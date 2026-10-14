//! Standard 7z archives using single-threaded LZMA2 streams.
use crate::{
    archive::ArchiveLimits,
    archive_safety::{
        self, collect, publish, regular_input, stage, write_entry, EntryPolicy, ReadLimits,
    },
    invalid, Stats,
};
use sevenz_rust2::{
    encoder_options::{EncoderOptions, Lzma2Options},
    ArchiveEntry, ArchiveReader, ArchiveWriter, EncoderConfiguration, EncoderMethod, SourceReader,
};
use std::{
    collections::{HashMap, HashSet},
    fs::{self, File},
    io::{self, Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
};

const DEFAULT_DICTIONARY: u32 = 16 * 1024 * 1024;
const MAX_DICTIONARY: u32 = 128 * 1024 * 1024;
const SEVEN_Z_MAGIC: &[u8; 6] = b"7z\xBC\xAF'\x1C";

#[derive(Debug, Clone)]
pub struct PackOptions {
    pub level: u32,
    pub solid: bool,
    pub dictionary_bytes: u32,
    pub threads: u32,
}
impl Default for PackOptions {
    fn default() -> Self {
        Self {
            level: 5,
            solid: true,
            dictionary_bytes: DEFAULT_DICTIONARY,
            threads: 1,
        }
    }
}

fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = !0u32;
    for &byte in bytes {
        crc ^= byte as u32;
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xEDB88320 & (0u32.wrapping_sub(crc & 1)));
        }
    }
    !crc
}

/// Validate the fixed 7z start header before the upstream parser allocates its next header.
fn preflight(path: &Path, limits: &ReadLimits) -> io::Result<()> {
    let file = regular_input(path, limits.max_compressed_bytes)?;
    let len = file.metadata()?.len();
    if len > usize::MAX as u64 {
        return Err(invalid(
            "7z archive does not fit this platform's address space",
        ));
    }
    if len < 32 {
        return Err(invalid("truncated 7z signature header"));
    }
    let mut fixed = [0u8; 32];
    (&file).take(32).read_exact(&mut fixed)?;
    if &fixed[..6] != SEVEN_Z_MAGIC {
        return Err(invalid("invalid 7z signature"));
    }
    if fixed[6] != 0 {
        return Err(invalid("unsupported 7z major version"));
    }
    let start_crc = u32::from_le_bytes(fixed[8..12].try_into().unwrap());
    if crc32(&fixed[12..32]) != start_crc {
        return Err(invalid("7z start-header CRC mismatch"));
    }
    let offset = u64::from_le_bytes(fixed[12..20].try_into().unwrap());
    let size = u64::from_le_bytes(fixed[20..28].try_into().unwrap());
    let crc = u32::from_le_bytes(fixed[28..32].try_into().unwrap());
    if size > limits.max_header_bytes {
        return Err(invalid("7z compressed header exceeds configured limit"));
    }
    let start = 32u64
        .checked_add(offset)
        .ok_or_else(|| invalid("7z header offset overflow"))?;
    let end = start
        .checked_add(size)
        .ok_or_else(|| invalid("7z header size overflow"))?;
    if start < 32 || end != len {
        return Err(invalid(
            "7z header bounds invalid or trailing bytes present",
        ));
    }
    let mut file = file;
    file.seek(SeekFrom::Start(start))?;
    let header_size =
        usize::try_from(size).map_err(|_| invalid("7z next header cannot fit in memory"))?;
    let mut header = Vec::with_capacity(header_size);
    file.take(size).read_to_end(&mut header)?;
    if header.len() as u64 != size {
        return Err(invalid("truncated 7z next header"));
    }
    if crc32(&header) != crc {
        return Err(invalid("7z next-header CRC mismatch"));
    }
    Ok(())
}

fn reader(path: &Path, limits: &ReadLimits) -> io::Result<ArchiveReader<File>> {
    preflight(path, limits)?;
    let file = regular_input(path, limits.max_compressed_bytes)?;
    let max_header = usize::try_from(limits.max_header_bytes)
        .map_err(|_| invalid("configured header limit cannot fit this platform"))?;
    let max_dictionary = usize::try_from(limits.max_dictionary_bytes.min(MAX_DICTIONARY as u64))
        .map_err(|_| invalid("configured dictionary limit cannot fit this platform"))?;
    ArchiveReader::new_with_limits(
        file,
        sevenz_rust2::Password::empty(),
        max_header,
        max_dictionary,
        usize::try_from(limits.archive.max_entries).unwrap_or(usize::MAX),
    )
    .map_err(|e| invalid(format!("invalid or unsupported 7z archive: {e}")))
}

fn validate_coders(ar: &sevenz_rust2::Archive, limits: &ReadLimits) -> io::Result<()> {
    let mut folder_total = 0u64;
    for block in &ar.blocks {
        folder_total = folder_total
            .checked_add(block.get_unpack_size())
            .ok_or_else(|| invalid("7z folder output size overflow"))?;
        if folder_total > limits.archive.max_total_bytes {
            return Err(invalid("7z folder output exceeds configured limit"));
        }
        for coder in &block.coders {
            let id = coder.encoder_method_id();
            if !matches!(
                id,
                [0x00]
                    | [0x03, 0x01, 0x01]
                    | [0x21]
                    | [0x03]
                    | [0x03, 0x03, 0x01, 0x03]
                    | [0x03, 0x03, 0x01, 0x1B]
                    | [0x03, 0x03, 0x02, 0x05]
                    | [0x03, 0x03, 0x04, 0x01]
                    | [0x03, 0x03, 0x05, 0x01]
                    | [0x03, 0x03, 0x07, 0x01]
                    | [0x03, 0x03, 0x08, 0x05]
                    | [0x0A]
                    | [0x0B]
            ) {
                return Err(invalid(format!("unsupported 7z coder method {id:02x?}")));
            }
            let dict = if id == [0x21] {
                let prop = *coder
                    .properties()
                    .first()
                    .ok_or_else(|| invalid("short LZMA2 properties"))?
                    as u32;
                if prop > 40 {
                    return Err(invalid("invalid LZMA2 dictionary property"));
                }
                if prop == 40 {
                    u32::MAX
                } else {
                    (2 | (prop & 1)) << (prop / 2 + 11)
                }
            } else if id == [0x03, 0x01, 0x01] {
                let p = coder.properties();
                if p.len() < 5 {
                    return Err(invalid("short LZMA properties"));
                }
                u32::from_le_bytes([p[1], p[2], p[3], p[4]])
            } else {
                0
            };
            if dict as u64 > limits.max_dictionary_bytes.min(MAX_DICTIONARY as u64) {
                return Err(invalid("7z dictionary exceeds configured limit"));
            }
        }
        if (0..block.coders.len())
            .any(|index| block.get_unpack_size_at_index(index) > limits.archive.max_total_bytes)
        {
            return Err(invalid(
                "7z coder intermediate output exceeds configured limit",
            ));
        }
    }
    Ok(())
}

type Inventory = (Vec<String>, HashMap<String, (bool, u64)>, u64);

fn inventory(ar: &sevenz_rust2::Archive, limits: &ArchiveLimits) -> io::Result<Inventory> {
    let mut policy = EntryPolicy::default();
    let mut names = Vec::with_capacity(ar.files.len());
    let mut items = HashMap::with_capacity(ar.files.len());
    let mut total = 0u64;
    for entry in &ar.files {
        if entry.is_anti_item {
            return Err(invalid("7z anti-items are unsupported"));
        }
        if entry.has_windows_attributes {
            let attrs = entry.windows_attributes;
            let unix_kind = (attrs >> 16) & 0xF000;
            if attrs & 0x400 != 0
                || (unix_kind != 0 && !matches!(unix_kind, 0x4000 | 0x8000))
                || (unix_kind == 0x4000 && !entry.is_directory)
                || (unix_kind == 0x8000 && entry.is_directory)
            {
                return Err(invalid(
                    "7z reparse points, links, and special files are unsupported",
                ));
            }
            if attrs & 0x10 != 0 && !entry.is_directory {
                return Err(invalid("7z directory attribute disagrees with entry type"));
            }
        }
        let is_dir = entry.is_directory;
        let size = if entry.has_stream { entry.size } else { 0 };
        let name = policy.add(&entry.name, is_dir, size, limits)?;
        if items.insert(name.clone(), (is_dir, size)).is_some() {
            return Err(invalid("duplicate 7z entry"));
        }
        names.push(name);
        total = total
            .checked_add(size)
            .ok_or_else(|| invalid("7z output size overflow"))?;
        if total > limits.max_total_bytes {
            return Err(invalid("7z output exceeds configured limit"));
        }
    }
    Ok((names, items, total))
}

struct LazyBoundedFile {
    path: PathBuf,
    file: Option<File>,
    expected: u64,
    seen: u64,
}
impl Read for LazyBoundedFile {
    fn read(&mut self, out: &mut [u8]) -> io::Result<usize> {
        if self.file.is_none() {
            let f = File::open(&self.path)?;
            if f.metadata()?.len() != self.expected {
                return Err(invalid("source file changed after archive preflight"));
            }
            self.file = Some(f);
        }
        if self.seen == self.expected {
            if self.file.as_ref().unwrap().metadata()?.len() != self.expected {
                return Err(invalid("source file changed during archive creation"));
            }
            return Ok(0);
        }
        let max = out.len().min((self.expected - self.seen) as usize);
        let n = self.file.as_mut().unwrap().read(&mut out[..max])?;
        if n == 0 {
            return Err(invalid("source file truncated during archive creation"));
        }
        self.seen += n as u64;
        Ok(n)
    }
}

pub fn pack<W: Write + Seek>(
    source: &Path,
    output: &mut W,
    opts: &PackOptions,
    limits: &ArchiveLimits,
) -> io::Result<Stats> {
    if opts.level > 9 {
        return Err(invalid("7z level must be between 0 and 9"));
    }
    if opts.threads != 1 {
        return Err(invalid("7z supports exactly one encoder thread"));
    }
    if !(4096..=MAX_DICTIONARY).contains(&opts.dictionary_bytes) {
        return Err(invalid("7z dictionary must be between 4 KiB and 128 MiB"));
    }
    let items = collect(source, limits)?;
    let input_bytes = items.iter().filter(|x| !x.is_dir).try_fold(0u64, |s, x| {
        s.checked_add(x.size)
            .ok_or_else(|| invalid("input size overflow"))
    })?;
    let mut writer =
        ArchiveWriter::new(&mut *output).map_err(|e| io::Error::other(e.to_string()))?;
    let mut lzma = Lzma2Options::from_level(opts.level);
    lzma.set_dictionary_size(opts.dictionary_bytes);
    let conf =
        EncoderConfiguration::new(EncoderMethod::LZMA2).with_options(EncoderOptions::Lzma2(lzma));
    writer.set_content_methods(vec![conf]);
    writer.set_encrypt_header(false);
    if opts.solid {
        let mut solid_entries = Vec::new();
        let mut solid_readers = Vec::new();
        for item in &items {
            if item.is_dir || item.size == 0 {
                let entry = if item.is_dir {
                    ArchiveEntry::new_directory(&item.name)
                } else {
                    ArchiveEntry::new_file(&item.name)
                };
                writer
                    .push_archive_entry(entry, Option::<io::Empty>::None)
                    .map_err(|e| io::Error::other(e.to_string()))?;
            } else {
                solid_entries.push(ArchiveEntry::new_file(&item.name));
                solid_readers.push(SourceReader::new(LazyBoundedFile {
                    path: item.path.clone(),
                    file: None,
                    expected: item.size,
                    seen: 0,
                }));
            }
        }
        if !solid_entries.is_empty() {
            writer
                .push_archive_entries(solid_entries, solid_readers)
                .map_err(|e| io::Error::other(e.to_string()))?;
        }
    } else {
        for item in &items {
            if item.is_dir || item.size == 0 {
                let entry = if item.is_dir {
                    ArchiveEntry::new_directory(&item.name)
                } else {
                    ArchiveEntry::new_file(&item.name)
                };
                writer
                    .push_archive_entry(entry, Option::<io::Empty>::None)
                    .map_err(|e| io::Error::other(e.to_string()))?;
            } else {
                let f = File::open(&item.path)?;
                if f.metadata()?.len() != item.size {
                    return Err(invalid("source file changed after archive preflight"));
                }
                let mut limited = f.take(item.size);
                writer
                    .push_archive_entry(ArchiveEntry::new_file(&item.name), Some(&mut limited))
                    .map_err(|e| io::Error::other(e.to_string()))?;
                if limited.limit() != 0 || fs::metadata(&item.path)?.len() != item.size {
                    return Err(invalid("source file changed during archive creation"));
                }
            }
        }
    }
    let finished = writer
        .finish()
        .map_err(|e| io::Error::other(format!("7z finish failed: {e}")))?;
    let end = finished.seek(SeekFrom::End(0))?;
    Ok(Stats {
        input_bytes,
        output_bytes: end,
    })
}

pub fn unpack(input: &Path, dest: &Path, limits: &ReadLimits) -> io::Result<Stats> {
    let mut r = reader(input, limits)?;
    validate_coders(r.archive(), limits)?;
    let (_names, declared, total) = inventory(r.archive(), &limits.archive)?;
    let stage = stage(dest)?;
    let mut seen = HashSet::new();
    let mut callback_error = None;
    r.for_each_entries(|entry, data| {
        let result = (|| {
            let name = archive_safety::normalize_name(&entry.name, entry.is_directory)?;
            let (is_dir, size) = declared
                .get(&name)
                .copied()
                .ok_or_else(|| invalid("decoded entry absent from validated metadata"))?;
            if is_dir != entry.is_directory || !seen.insert(name.clone()) {
                return Err(invalid("duplicate or changed 7z entry"));
            }
            write_entry(stage.path(), &name, is_dir, size, data)
        })();
        if let Err(error) = result {
            callback_error = Some(error);
            return Ok(false);
        }
        Ok(true)
    })
    .map_err(|e| invalid(format!("7z integrity or decode failure: {e}")))?;
    if let Some(error) = callback_error {
        return Err(error);
    }
    if seen.len() != declared.len() {
        return Err(invalid("7z decoder did not visit every metadata entry"));
    }
    publish(&stage, dest)?;
    let compressed_bytes = fs::metadata(input)?.len();
    Ok(Stats {
        input_bytes: compressed_bytes,
        output_bytes: total,
    })
}

pub fn test(input: &Path, limits: &ReadLimits) -> io::Result<Stats> {
    let mut r = reader(input, limits)?;
    validate_coders(r.archive(), limits)?;
    let (_names, declared, total) = inventory(r.archive(), &limits.archive)?;
    let mut seen = HashSet::new();
    let mut decoded = 0u64;
    let mut callback_error = None;
    r.for_each_entries(|entry, data| {
        let result = (|| {
            let name = archive_safety::normalize_name(&entry.name, entry.is_directory)?;
            let (is_dir, size) = declared
                .get(&name)
                .copied()
                .ok_or_else(|| invalid("decoded entry absent from validated metadata"))?;
            if is_dir != entry.is_directory || !seen.insert(name) {
                return Err(invalid("duplicate or changed 7z entry"));
            }
            let mut sink = io::sink();
            let count = io::copy(data, &mut sink)?;
            if count != size {
                return Err(invalid("7z entry length mismatch"));
            }
            decoded += count;
            Ok(())
        })();
        if let Err(error) = result {
            callback_error = Some(error);
            return Ok(false);
        }
        Ok(true)
    })
    .map_err(|e| invalid(format!("7z integrity or decode failure: {e}")))?;
    if let Some(error) = callback_error {
        return Err(error);
    }
    if seen.len() != declared.len() || decoded != total {
        return Err(invalid("7z validation did not cover all entries"));
    }
    Ok(Stats {
        input_bytes: fs::metadata(input)?.len(),
        output_bytes: decoded,
    })
}

pub fn info(input: &Path, limits: &ReadLimits) -> io::Result<serde_json::Value> {
    let r = reader(input, limits)?;
    validate_coders(r.archive(), limits)?;
    let (names, entries, total) = inventory(r.archive(), &limits.archive)?;
    let files = names.iter().map(|name| {
        let (is_dir, size) = entries[name];
        serde_json::json!({"name": name, "type": if is_dir { "directory" } else { "file" }, "size": size})
    }).collect::<Vec<_>>();
    Ok(serde_json::json!({
        "format": "7z", "entry_count": entries.len(), "uncompressed_bytes": total,
        "solid": r.archive().is_solid, "integrity_validated": false, "files": files
    }))
}
