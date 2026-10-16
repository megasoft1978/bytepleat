//! Bounded ZIP Stored/Deflate adapter. ZIP headers are preflighted before the
//! upstream reader builds its central-directory index.
use crate::{archive::ArchiveLimits, archive_safety as safe, invalid, Stats};
use serde_json::json;
use std::{
    fs,
    fs::File,
    io::{self, Read, Seek, SeekFrom, Write},
    path::Path,
};
use zip::{write::SimpleFileOptions, CompressionMethod, DateTime, ZipArchive, ZipWriter};

const ZIP_LIMIT: u64 = 1024 * 1024 * 1024;
#[derive(Debug, Clone)]
pub struct PackOptions {
    pub level: i32,
    pub stored: bool,
}
impl Default for PackOptions {
    fn default() -> Self {
        Self {
            level: 6,
            stored: false,
        }
    }
}

fn le16(b: &[u8], p: usize) -> u16 {
    u16::from_le_bytes([b[p], b[p + 1]])
}
fn le32(b: &[u8], p: usize) -> u32 {
    u32::from_le_bytes([b[p], b[p + 1], b[p + 2], b[p + 3]])
}
/// Locate and validate a classic EOCD and bound directory parsing before ZipArchive::new.
fn precheck(f: &mut File, limits: &safe::ReadLimits) -> io::Result<(u64, u64, u16)> {
    let len = f.metadata()?.len();
    if len > limits.max_compressed_bytes.min(ZIP_LIMIT) {
        return Err(invalid("compressed ZIP exceeds input limit"));
    }
    if len < 22 {
        return Err(invalid("truncated ZIP EOCD"));
    }
    let n = (len.min(22 + 65535)) as usize;
    f.seek(SeekFrom::End(-(n as i64)))?;
    let mut tail = vec![0; n];
    f.read_exact(&mut tail)?;
    let pos = (0..=n - 22)
        .rev()
        .find(|&i| tail[i..i + 4] == [0x50, 0x4b, 0x05, 0x06])
        .ok_or_else(|| invalid("ZIP EOCD not found"))?;
    let e = &tail[pos..];
    let comment = le16(e, 20) as usize;
    if pos + 22 + comment != n {
        return Err(invalid("trailing junk or malformed ZIP comment"));
    }
    if le16(e, 4) != 0 || le16(e, 6) != 0 || le16(e, 8) != le16(e, 10) {
        return Err(invalid("multidisk ZIP unsupported"));
    }
    let count = le16(e, 10);
    let size = le32(e, 12) as u64;
    let off = le32(e, 16) as u64;
    let eocd = len - n as u64 + pos as u64;
    if count == u16::MAX || size == u32::MAX as u64 || off == u32::MAX as u64 {
        return Err(invalid("ZIP64 unsupported"));
    }
    if count as u64 > limits.archive.max_entries {
        return Err(invalid("ZIP entry limit exceeded"));
    }
    if size > limits.max_header_bytes || off.checked_add(size) != Some(eocd) {
        return Err(invalid("invalid or oversized ZIP central directory"));
    }
    // Scan fixed central records, checking bounds, ZIP64 markers, and flags/codecs
    // before the crate allocates its metadata index.
    f.seek(SeekFrom::Start(off))?;
    let mut consumed = 0u64;
    let mut local_records = Vec::with_capacity(count as usize);
    for _ in 0..count {
        let mut h = [0; 46];
        f.read_exact(&mut h)?;
        consumed += 46;
        if h[..4] != [0x50, 0x4b, 0x01, 0x02] {
            return Err(invalid("malformed ZIP central directory"));
        }
        if consumed > size {
            return Err(invalid("ZIP central record exceeds bounds"));
        }
        let local = le32(&h, 42) as u64;
        if le16(&h, 34) != 0 || local == u32::MAX as u64 || local >= off {
            return Err(invalid("invalid ZIP local offset or split archive"));
        }
        let flags = le16(&h, 8);
        let method = le16(&h, 10);
        let c = le32(&h, 20);
        let u = le32(&h, 24);
        let nl = le16(&h, 28) as u64;
        let xl = le16(&h, 30) as u64;
        let cl = le16(&h, 32) as u64;
        if flags & 1 != 0 || flags & 0x40 != 0 {
            return Err(invalid("encrypted ZIP entries unsupported"));
        }
        if !matches!(method, 0 | 8) {
            return Err(invalid("unsupported ZIP compression method"));
        }
        if c == u32::MAX || u == u32::MAX {
            return Err(invalid("ZIP64 unsupported"));
        }
        if xl > limits.max_header_bytes {
            return Err(invalid("ZIP extra field exceeds header limit"));
        }
        let variable = nl
            .checked_add(xl)
            .and_then(|x| x.checked_add(cl))
            .ok_or_else(|| invalid("ZIP header size overflow"))?;
        if variable > size.saturating_sub(consumed) {
            return Err(invalid("ZIP central record exceeds bounds"));
        }
        let mut variable_data = vec![0; (nl + xl) as usize];
        f.read_exact(&mut variable_data)?;
        std::str::from_utf8(&variable_data[..nl as usize])
            .map_err(|_| invalid("ZIP entry name is not UTF-8"))?;
        if flags & 0x800 == 0 && !variable_data[..nl as usize].iter().all(u8::is_ascii) {
            return Err(invalid("non-ASCII ZIP names must use the UTF-8 flag"));
        }
        local_records.push((
            local,
            flags,
            method,
            c as u64,
            variable_data[..nl as usize].to_vec(),
        ));
        // ZIP extra fields are bounded above and are TLV encoded. Reject ZIP64
        // before the upstream parser can interpret replacement sizes/offsets.
        let mut at = nl as usize;
        while at < variable_data.len() {
            if at + 4 > variable_data.len() {
                return Err(invalid("malformed ZIP extra field"));
            }
            let tag = le16(&variable_data, at);
            let n = le16(&variable_data, at + 2) as usize;
            at += 4;
            if at + n > variable_data.len() {
                return Err(invalid("malformed ZIP extra field length"));
            }
            if tag == 1 {
                return Err(invalid("ZIP64 unsupported"));
            }
            at += n;
        }
        let mut discard = [0; 4096];
        let mut left = cl;
        while left > 0 {
            let n = left.min(discard.len() as u64) as usize;
            f.read_exact(&mut discard[..n])?;
            left -= n as u64;
        }
        consumed = consumed
            .checked_add(variable)
            .ok_or_else(|| invalid("ZIP directory size overflow"))?;
        if consumed > size {
            return Err(invalid("ZIP central directory exceeds bounds"));
        }
    }
    if consumed != size {
        return Err(invalid("unexpected bytes in ZIP central directory"));
    }
    local_records.sort_by_key(|x| x.0);
    let mut next = 0u64;
    for (local, flags, method, compressed, name) in local_records {
        if local != next {
            return Err(invalid("ZIP has overlapping or unreferenced payload"));
        }
        f.seek(SeekFrom::Start(local))?;
        let mut h = [0u8; 30];
        f.read_exact(&mut h)?;
        if h[..4] != [0x50, 0x4b, 0x03, 0x04] || le16(&h, 6) != flags || le16(&h, 8) != method {
            return Err(invalid("ZIP local and central headers disagree"));
        }
        let nl = le16(&h, 26) as usize;
        let xl = le16(&h, 28) as usize;
        let mut variable = vec![0u8; nl + xl];
        f.read_exact(&mut variable)?;
        if variable[..nl] != name {
            return Err(invalid("ZIP local entry name mismatch"));
        }
        let mut at = nl;
        while at < variable.len() {
            if at + 4 > variable.len() {
                return Err(invalid("malformed local ZIP extra"));
            }
            let tag = le16(&variable, at);
            let n = le16(&variable, at + 2) as usize;
            at += 4;
            if tag == 1 || at + n > variable.len() {
                return Err(invalid("ZIP64 or malformed local extra unsupported"));
            }
            at += n;
        }
        next = local
            .checked_add(30 + nl as u64 + xl as u64)
            .and_then(|v| v.checked_add(compressed))
            .filter(|v| *v <= off)
            .ok_or_else(|| invalid("ZIP payload exceeds bounds"))?;
        if flags & 8 != 0 {
            f.seek(SeekFrom::Start(next))?;
            let mut descriptor = [0u8; 4];
            f.read_exact(&mut descriptor)?;
            next = next
                .checked_add(if descriptor == [0x50, 0x4b, 0x07, 0x08] {
                    16
                } else {
                    12
                })
                .ok_or_else(|| invalid("ZIP descriptor overflow"))?;
        }
    }
    if next != off {
        return Err(invalid("ZIP contains unreferenced data"));
    }
    Ok((off, size, count))
}
fn archive(path: &Path, l: &safe::ReadLimits) -> io::Result<(ZipArchive<File>, u64)> {
    let mut f = safe::regular_input(path, l.max_compressed_bytes.min(ZIP_LIMIT))?;
    let (_, _, declared_count) = precheck(&mut f, l)?;
    let n = f.metadata()?.len();
    let a = ZipArchive::new(f).map_err(|e| invalid(e.to_string()))?;
    // The upstream index collapses exact duplicate names. Never silently drop entries.
    if a.len() != declared_count as usize {
        return Err(invalid("ZIP duplicate names or metadata index mismatch"));
    }
    Ok((a, n))
}
fn preflight<R: Read + Seek>(
    a: &mut ZipArchive<R>,
    l: &safe::ReadLimits,
) -> io::Result<Vec<(String, bool, u64)>> {
    let mut policy = safe::EntryPolicy::default();
    let mut entries = Vec::with_capacity(a.len());
    let mut seen_root = false;
    for i in 0..a.len() {
        let z = a.by_index(i).map_err(|e| invalid(e.to_string()))?;
        if z.encrypted() {
            return Err(invalid("encrypted ZIP entries unsupported"));
        }
        let dos_attributes = z.external_attributes() & 0xffff;
        if dos_attributes & (0x02 | 0x04 | 0x08) != 0 {
            return Err(invalid("unsafe ZIP DOS attributes"));
        }
        if !matches!(
            z.compression(),
            CompressionMethod::Stored | CompressionMethod::Deflated
        ) {
            return Err(invalid("unsupported ZIP compression method"));
        }
        if let Some(mode) = z.unix_mode() {
            let kind = mode & 0o170000;
            if kind != 0 && kind != 0o100000 && kind != 0o040000 {
                return Err(invalid("ZIP links and special files unsupported"));
            }
            if (kind == 0o040000 && !z.is_dir()) || (kind == 0o100000 && z.is_dir()) {
                return Err(invalid("ZIP entry attributes disagree with name"));
            }
            if mode & 0o6000 != 0 {
                return Err(invalid("unsafe ZIP Unix attributes"));
            }
        }
        let dir = z.is_dir();
        if dir && z.size() != 0 {
            return Err(invalid("directory has nonzero size"));
        }
        let name = z.name().map_err(|e| invalid(e.to_string()))?.into_owned();
        // bsdtar-style archives rooted at `.` carry one bare `./` directory entry.
        // Keep an empty-named placeholder so indexes stay aligned; `decode` skips it.
        if dir && name == "./" {
            if std::mem::replace(&mut seen_root, true) {
                return Err(invalid("duplicate archive entry"));
            }
            entries.push((String::new(), true, 0));
            continue;
        }
        let normalized = policy.add(&name, dir, z.size(), &l.archive)?;
        entries.push((normalized, dir, z.size()));
    }
    Ok(entries)
}
fn decode<R: Read + Seek>(
    a: &mut ZipArchive<R>,
    entries: &[(String, bool, u64)],
    stage: Option<&Path>,
    l: &safe::ReadLimits,
) -> io::Result<u64> {
    let mut total = 0u64;
    let mut buf = [0u8; 64 * 1024];
    for (i, (name, dir, size)) in entries.iter().enumerate() {
        let mut z = a.by_index(i).map_err(|e| invalid(e.to_string()))?;
        if *dir {
            if z.read(&mut buf[..1])? != 0 {
                return Err(invalid("ZIP directory contains data"));
            }
            if name.is_empty() {
                continue;
            }
            if let Some(root) = stage {
                safe::write_entry(root, name, true, 0, &mut io::empty())?
            }
            continue;
        }
        let mut out = if let Some(root) = stage {
            let p = root.join(name);
            if let Some(parent) = p.parent() {
                fs::create_dir_all(parent)?;
            }
            Some(
                std::fs::OpenOptions::new()
                    .write(true)
                    .create_new(true)
                    .open(p)?,
            )
        } else {
            None
        };
        let mut actual = 0u64;
        loop {
            let n = z.read(&mut buf)?;
            if n == 0 {
                break;
            }
            actual = actual
                .checked_add(n as u64)
                .ok_or_else(|| invalid("ZIP decoded size overflow"))?;
            total = total
                .checked_add(n as u64)
                .ok_or_else(|| invalid("ZIP output size overflow"))?;
            if actual > *size || total > l.archive.max_total_bytes {
                return Err(invalid("ZIP decoded output limit exceeded"));
            }
            if let Some(o) = out.as_mut() {
                o.write_all(&buf[..n])?
            }
        }
        if actual != *size {
            return Err(invalid("ZIP decoded size mismatch or truncation"));
        }
        if let Some(o) = out.as_mut() {
            o.flush()?
        }
    }
    Ok(total)
}
pub fn unpack(input: &Path, dest: &Path, l: &safe::ReadLimits) -> io::Result<Stats> {
    let (mut a, n) = archive(input, l)?;
    let e = preflight(&mut a, l)?;
    let stage = safe::stage(dest)?;
    decode(&mut a, &e, Some(stage.path()), l)?;
    safe::publish(&stage, dest)?;
    Ok(Stats {
        input_bytes: n,
        output_bytes: e.iter().map(|x| x.2).sum(),
    })
}
pub fn test(input: &Path, l: &safe::ReadLimits) -> io::Result<Stats> {
    let (mut a, n) = archive(input, l)?;
    let e = preflight(&mut a, l)?;
    let out = decode(&mut a, &e, None, l)?;
    Ok(Stats {
        input_bytes: n,
        output_bytes: out,
    })
}
pub fn info(input: &Path, l: &safe::ReadLimits) -> io::Result<serde_json::Value> {
    let (mut a, n) = archive(input, l)?;
    let e = preflight(&mut a, l)?;
    Ok(
        json!({"format":"zip","entries":e.len(),"input_bytes":n,"declared_output_bytes":e.iter().map(|x|x.2).sum::<u64>(),"integrity_validated":false}),
    )
}
pub fn pack<W: Write + io::Seek>(
    source: &Path,
    output: &mut W,
    o: &PackOptions,
    l: &ArchiveLimits,
) -> io::Result<Stats> {
    if !(0..=9).contains(&o.level) {
        return Err(invalid("ZIP level must be 0..9"));
    }
    let items = safe::collect(source, l)?;
    if items.len() >= u16::MAX as usize {
        return Err(invalid("classic ZIP entry limit exceeded"));
    }
    let start = output.stream_position()?;
    let mut z = ZipWriter::new(output);
    for item in &items {
        let method = if o.stored {
            CompressionMethod::Stored
        } else {
            CompressionMethod::Deflated
        };
        let mut opts = SimpleFileOptions::default()
            .compression_method(method)
            .compression_level(if o.stored { None } else { Some(o.level.into()) });
        let name = if item.is_dir {
            format!("{}/", item.name)
        } else {
            item.name.clone()
        };
        if l.deterministic {
            opts = opts.last_modified_time(DateTime::default_for_write())
        }
        if item.is_dir {
            z.add_directory(
                name,
                opts.compression_method(CompressionMethod::Stored)
                    .compression_level(None),
            )
            .map_err(|e| invalid(e.to_string()))?;
        } else {
            z.start_file(name, opts)
                .map_err(|e| invalid(e.to_string()))?;
        }
        if !item.is_dir {
            let mut f = File::open(&item.path)?;
            if f.metadata()?.len() != item.size {
                return Err(invalid("input changed after ZIP preflight"));
            }
            let copied = io::copy(&mut f, &mut z)?;
            if copied != item.size || fs::metadata(&item.path)?.len() != item.size {
                return Err(invalid("input changed during ZIP creation"));
            }
        }
    }
    let output = z.finish().map_err(|e| invalid(e.to_string()))?;
    output.flush()?;
    let end = output.stream_position()?;
    if end - start > ZIP_LIMIT {
        return Err(invalid("created ZIP exceeds supported size limit"));
    }
    Ok(Stats {
        input_bytes: items.iter().map(|x| x.size).sum(),
        output_bytes: end - start,
    })
}
