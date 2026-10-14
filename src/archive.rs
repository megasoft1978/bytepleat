//! Safe, portable directory archives carried by the ordinary gzip, zstd, or
//! LZ4 frame formats. Archive paths are always relative to the packed root.
use crate::{codecs, invalid, DecodeOptions, EncodeOptions, Format, Stats};
use std::{
    collections::HashSet,
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    path::{Component, Path, PathBuf},
    time::UNIX_EPOCH,
};
use unicode_normalization::UnicodeNormalization;
use walkdir::WalkDir;

/// Resource and reproducibility controls for directory archives.
#[derive(Debug, Clone)]
pub struct ArchiveLimits {
    pub max_entries: u64,
    pub max_total_bytes: u64,
    pub max_depth: usize,
    pub deterministic: bool,
}
impl Default for ArchiveLimits {
    fn default() -> Self {
        Self {
            max_entries: 100_000,
            max_total_bytes: 1024 * 1024 * 1024,
            max_depth: 64,
            deterministic: false,
        }
    }
}

#[derive(Debug)]
struct Item {
    path: PathBuf,
    rel: String,
    dir: bool,
    size: u64,
    mode: u32,
}

fn supported(format: Format) -> io::Result<()> {
    if format == Format::Pco {
        Err(invalid(
            "Pco is a typed numeric format and cannot encode tar archives",
        ))
    } else {
        Ok(())
    }
}

fn valid_component(s: &str) -> bool {
    if s.is_empty()
        || s == "."
        || s == ".."
        || s.ends_with('.')
        || s.ends_with(' ')
        || s.contains(['\\', ':', '\0'])
    {
        return false;
    }
    let stem = s.split('.').next().unwrap_or("").to_ascii_uppercase();
    if matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL" | "CLOCK$") {
        return false;
    }
    if let Some(n) = stem
        .strip_prefix("COM")
        .or_else(|| stem.strip_prefix("LPT"))
    {
        if matches!(
            n,
            "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "¹" | "²" | "³"
        ) {
            return false;
        }
    }
    true
}
fn portable_rel(path: &Path) -> io::Result<String> {
    let mut out = Vec::new();
    for c in path.components() {
        match c {
            Component::Normal(x) => {
                let s = x
                    .to_str()
                    .ok_or_else(|| invalid("archive path is not UTF-8"))?;
                if !valid_component(s) {
                    return Err(invalid("archive path contains a non-portable component"));
                }
                out.push(s);
            }
            _ => return Err(invalid("archive path is not root-relative")),
        }
    }
    if out.is_empty() {
        return Err(invalid("empty archive path"));
    }
    Ok(out.join("/"))
}
fn collision_key(rel: &str) -> String {
    rel.split('/')
        .map(|x| {
            x.nfc()
                .collect::<String>()
                .to_lowercase()
                .nfc()
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("/")
}

fn preflight(root: &Path, limits: &ArchiveLimits) -> io::Result<Vec<Item>> {
    let md = fs::symlink_metadata(root)?;
    if !md.file_type().is_dir() || md.file_type().is_symlink() {
        return Err(invalid("archive root must be a real directory"));
    }
    let root = fs::canonicalize(root)?;
    let mut items = Vec::new();
    let mut total = 0u64;
    let mut names = HashSet::new();
    for ent in WalkDir::new(&root).follow_links(false).min_depth(1) {
        let ent = ent.map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
        let ft = ent.file_type();
        if !(ft.is_dir() || ft.is_file()) {
            return Err(invalid("archive input contains a link or special file"));
        }
        let rel = portable_rel(
            ent.path()
                .strip_prefix(&root)
                .map_err(|_| invalid("path escaped archive root"))?,
        )?;
        let key = collision_key(&rel);
        if !names.insert(key) {
            return Err(invalid("case-insensitive archive path collision"));
        }
        if ent.depth() > limits.max_depth {
            return Err(invalid("archive depth limit exceeded"));
        }
        let size = if ft.is_file() {
            ent.metadata()
                .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?
                .len()
        } else {
            0
        };
        total = total
            .checked_add(size)
            .ok_or_else(|| invalid("archive byte count overflow"))?;
        items.push(Item {
            path: ent.path().to_path_buf(),
            rel,
            dir: ft.is_dir(),
            size,
            mode: if ft.is_dir() { 0o755 } else { 0o644 },
        });
        if items.len() as u64 > limits.max_entries {
            return Err(invalid("archive entry limit exceeded"));
        }
        if total > limits.max_total_bytes {
            return Err(invalid("archive byte limit exceeded"));
        }
    }
    // Parent directories precede descendants; sorted pathnames are reproducible.
    items.sort_by(|a, b| a.rel.cmp(&b.rel));
    for i in &mut items {
        if !i.dir {
            #[cfg(unix)]
            let m = fs::metadata(&i.path)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                i.mode = if m.permissions().mode() & 0o111 != 0 {
                    0o755
                } else {
                    0o644
                };
            }
        }
    }
    Ok(items)
}

/// Pack a directory tree. Files are rechecked while read so concurrent changes fail.
pub fn pack<W: Write>(
    root: &Path,
    output: W,
    opts: &EncodeOptions,
    limits: &ArchiveLimits,
) -> io::Result<Stats> {
    supported(opts.format)?;
    let items = preflight(root, limits)?;
    codecs::encode_with(output, opts, |compressed| {
        let mut builder = tar::Builder::new(compressed);
        builder.mode(tar::HeaderMode::Deterministic);
        for item in &items {
            // GNU headers let the tar builder emit its standard long-name
            // extension for paths which do not fit in USTAR.
            let mut h = tar::Header::new_gnu();
            h.set_entry_type(if item.dir {
                tar::EntryType::Directory
            } else {
                tar::EntryType::Regular
            });
            h.set_size(item.size);
            h.set_mode(item.mode);
            h.set_uid(0);
            h.set_gid(0);
            h.set_mtime(if limits.deterministic {
                0
            } else {
                item.path
                    .metadata()?
                    .modified()
                    .ok()
                    .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                    .map(|d| d.as_secs())
                    .unwrap_or(0)
            });
            h.set_username("").map_err(|e| invalid(e.to_string()))?;
            h.set_groupname("").map_err(|e| invalid(e.to_string()))?;
            h.set_cksum();
            let name = if item.dir {
                format!("{}/", item.rel)
            } else {
                item.rel.clone()
            };
            if item.dir {
                builder.append_data(&mut h, name, io::empty())?;
            } else {
                let f = File::open(&item.path)?;
                let before = f.metadata()?.len();
                if before != item.size {
                    return Err(invalid("input file changed after archive preflight"));
                }
                let mut limited = f.take(item.size);
                builder.append_data(&mut h, name, &mut limited)?;
                if limited.limit() != 0 {
                    return Err(invalid("input file was truncated during archive creation"));
                }
                let now = fs::metadata(&item.path)?.len();
                if now != item.size {
                    return Err(invalid("input file changed during archive creation"));
                }
            }
        }
        builder.finish()?;
        Ok(())
    })
}

fn ensure_safe_path(raw: &Path) -> io::Result<(PathBuf, String)> {
    let s = raw
        .to_str()
        .ok_or_else(|| invalid("tar path is not UTF-8"))?;
    if s.is_empty()
        || s.starts_with('/')
        || s.starts_with('\\')
        || s.contains('\\')
        || s.contains(':')
        || s.contains('\0')
    {
        return Err(invalid("unsafe absolute or non-portable tar path"));
    }
    let trimmed = s.strip_suffix('/').unwrap_or(s);
    let normalized = trimmed
        .split('/')
        .filter(|c| *c != ".")
        .collect::<Vec<_>>()
        .join("/");
    let rel = portable_rel(Path::new(&normalized))?;
    Ok((rel.split('/').collect::<PathBuf>(), rel))
}

fn metadata_payload<R: Read>(e: &mut tar::Entry<'_, R>) -> io::Result<Vec<u8>> {
    let size = e.header().size()?;
    if size > 64 * 1024 {
        return Err(invalid("tar metadata header exceeds 64 KiB"));
    }
    let mut data = Vec::with_capacity(size as usize);
    e.take(size).read_to_end(&mut data)?;
    if data.len() as u64 != size {
        return Err(invalid("truncated tar metadata header"));
    }
    Ok(data)
}

fn parse_pax(data: &[u8]) -> io::Result<Option<String>> {
    let mut at = 0usize;
    let mut path = None;
    while at < data.len() {
        let space = data[at..]
            .iter()
            .position(|b| *b == b' ')
            .ok_or_else(|| invalid("malformed PAX record length"))?
            + at;
        if space == at || !data[at..space].iter().all(u8::is_ascii_digit) {
            return Err(invalid("malformed PAX record length"));
        }
        let n: usize = std::str::from_utf8(&data[at..space])
            .unwrap()
            .parse()
            .map_err(|_| invalid("malformed PAX record length"))?;
        let end = at
            .checked_add(n)
            .filter(|end| *end <= data.len())
            .ok_or_else(|| invalid("PAX record exceeds metadata payload"))?;
        if n <= space - at + 1 || data[end - 1] != b'\n' {
            return Err(invalid("malformed PAX record"));
        }
        let record = &data[space + 1..end - 1];
        let eq = record
            .iter()
            .position(|b| *b == b'=')
            .ok_or_else(|| invalid("malformed PAX key/value"))?;
        let key = &record[..eq];
        let value = &record[eq + 1..];
        if key == b"size" {
            return Err(invalid("PAX size overrides are unsupported"));
        }
        if key == b"path" {
            if path.is_some() {
                return Err(invalid("duplicate PAX path"));
            }
            path = Some(
                std::str::from_utf8(value)
                    .map_err(|_| invalid("PAX path is not UTF-8"))?
                    .to_owned(),
            );
        } else if !matches!(
            key,
            b"mtime" | b"atime" | b"ctime" | b"uid" | b"gid" | b"uname" | b"gname"
        ) {
            return Err(invalid("unsupported PAX attribute"));
        }
        at = end;
    }
    Ok(path)
}

/// Extract a supported tar stream into a new destination directory.
pub fn unpack<R: Read>(
    input: R,
    dest: &Path,
    opts: &DecodeOptions,
    limits: &ArchiveLimits,
) -> io::Result<Stats> {
    // The codec is detected from the input stream; Pco is rejected by decode_with.
    if fs::symlink_metadata(dest).is_ok() {
        return Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            "destination already exists",
        ));
    }
    let parent = dest
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let pmd = fs::symlink_metadata(parent)?;
    if !pmd.is_dir() || pmd.file_type().is_symlink() {
        return Err(invalid(
            "destination parent must be an existing real directory",
        ));
    }
    let stage = tempfile::Builder::new()
        .prefix(".bytepleat-extract-")
        .tempdir_in(parent)?;
    let stage_path = stage.path().to_path_buf();
    let stats = codecs::decode_with(input, opts, |decoded| {
        let mut archive = tar::Archive::new(TarCounter {
            inner: decoded,
            position: 0,
        });
        let mut record_end = 0u64;
        let mut keys = HashSet::new();
        let mut kinds = std::collections::HashMap::<String, (bool, bool, String)>::new();
        let mut count = 0u64;
        let mut total = 0u64;
        let mut pending_path: Option<String> = None;
        let mut pending_metadata = false;
        for entry in archive.entries()?.raw(true) {
            let mut e = entry?;
            let ty = e.header().entry_type();
            let payload_bytes = e.header().size()?;
            record_end = record_end
                .checked_add(512)
                .and_then(|v| {
                    payload_bytes
                        .div_ceil(512)
                        .checked_mul(512)
                        .and_then(|n| v.checked_add(n))
                })
                .ok_or_else(|| invalid("tar position overflow"))?;
            count += 1;
            if count > limits.max_entries {
                return Err(invalid("archive entry limit exceeded"));
            }
            if ty.is_pax_global_extensions() || ty.is_gnu_longlink() || ty.is_gnu_sparse() {
                return Err(invalid("tar contains a link, sparse, or special entry"));
            }
            if ty.is_gnu_longname() || ty.is_pax_local_extensions() {
                if pending_metadata {
                    return Err(invalid("multiple pending tar path headers"));
                }
                let payload = metadata_payload(&mut e)?;
                pending_metadata = true;
                if ty.is_gnu_longname() {
                    if payload.len() < 2
                        || payload.last() != Some(&0)
                        || payload[..payload.len() - 1].contains(&0)
                    {
                        return Err(invalid("invalid GNU long-name payload"));
                    }
                    pending_path = Some(
                        std::str::from_utf8(&payload[..payload.len() - 1])
                            .map_err(|_| invalid("GNU long name is not UTF-8"))?
                            .to_owned(),
                    );
                } else {
                    pending_path = parse_pax(&payload)?;
                }
                continue;
            }
            if !(ty.is_file() || ty.is_dir()) {
                return Err(invalid("tar contains a link or special entry"));
            }
            pending_metadata = false;
            let raw = if let Some(path) = pending_path.take() {
                PathBuf::from(path)
            } else {
                e.path()?.into_owned()
            };
            if ty.is_dir()
                && !raw.as_os_str().is_empty()
                && raw
                    .components()
                    .all(|c| matches!(c, std::path::Component::CurDir))
            {
                if payload_bytes != 0 {
                    return Err(invalid("tar root directory carries data"));
                }
                continue;
            }
            let header_path = e.header().path_bytes();
            if header_path.contains(&b'\\') {
                return Err(invalid("tar header path contains a backslash"));
            }
            let (relpath, rel) = ensure_safe_path(&raw)?;
            let key = collision_key(&rel);
            let same_key = !keys.insert(key.clone());
            let depth = rel.split('/').count();
            if depth > limits.max_depth {
                return Err(invalid("archive depth limit exceeded"));
            }
            let is_dir = ty.is_dir();
            for (i, _) in rel.split('/').enumerate().take(depth.saturating_sub(1)) {
                let ancestor = rel.split('/').take(i + 1).collect::<Vec<_>>().join("/");
                let ancestor_key = collision_key(&ancestor);
                if kinds
                    .get(&ancestor_key)
                    .is_some_and(|(is_dir, _, spelling)| !is_dir || spelling != &ancestor)
                {
                    return Err(invalid("file is an ancestor of another entry"));
                }
                kinds.entry(ancestor_key).or_insert((true, false, ancestor));
            }
            let folded = collision_key(&rel);
            if same_key {
                if let Some((true, false, spelling)) = kinds.get(&folded) {
                    if spelling != &rel {
                        return Err(invalid("case-folded directory alias"));
                    }
                    if is_dir {
                        kinds.insert(folded.clone(), (true, true, rel.clone()));
                    } else {
                        return Err(invalid("duplicate or case-fold-colliding tar path"));
                    }
                } else {
                    return Err(invalid("duplicate or case-fold-colliding tar path"));
                }
            } else {
                kinds.insert(folded, (is_dir, true, rel.clone()));
            }
            let out = stage_path.join(&relpath);
            if is_dir {
                if payload_bytes != 0 {
                    return Err(invalid("tar directory carries data"));
                }
                fs::create_dir_all(&out)?;
            } else {
                if let Some(p) = out.parent() {
                    fs::create_dir_all(p)?;
                }
                let size = e.header().size()?;
                total = total
                    .checked_add(size)
                    .ok_or_else(|| invalid("archive byte count overflow"))?;
                if total > limits.max_total_bytes || total > opts.max_output {
                    return Err(invalid("archive byte limit exceeded"));
                }
                let mut f = OpenOptions::new().write(true).create_new(true).open(&out)?;
                let copied = io::copy(&mut e, &mut f)?;
                if copied != size {
                    return Err(invalid("truncated tar entry"));
                }
                f.flush()?;
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    f.set_permissions(fs::Permissions::from_mode(e.header().mode()? & 0o777))?;
                }
            }
        }
        if pending_metadata || pending_path.is_some() {
            return Err(invalid("dangling tar path metadata"));
        }
        let mut tail = archive.into_inner();
        let mut buf = [0u8; 8192];
        loop {
            let n = tail.read(&mut buf)?;
            if n == 0 {
                break;
            }
            if buf[..n].iter().any(|b| *b != 0) {
                return Err(invalid("non-zero data follows tar end marker"));
            }
        }
        if tail.position
            < record_end
                .checked_add(1024)
                .ok_or_else(|| invalid("tar end marker overflow"))?
        {
            return Err(invalid("missing complete tar end marker"));
        }
        Ok(())
    })?;
    // Publish without replacing an existing destination. The reservation blocks
    // a competing creator; on failure, remove only this invocation's empty reservation.
    fs::create_dir(dest)?;
    let mut moved = Vec::new();
    let result = (|| {
        for entry in fs::read_dir(&stage_path)? {
            let entry = entry?;
            let target = dest.join(entry.file_name());
            fs::rename(entry.path(), &target)?;
            moved.push(target);
        }
        Ok::<(), io::Error>(())
    })();
    if let Err(err) = result {
        return Err(crate::archive_safety::rollback_publication(
            &stage_path,
            dest,
            moved,
            err,
        ));
    }
    Ok(stats)
}

struct TarCounter<'a> {
    inner: &'a mut dyn Read,
    position: u64,
}
impl Read for TarCounter<'_> {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        let n = self.inner.read(buf)?;
        self.position = self
            .position
            .checked_add(n as u64)
            .ok_or_else(|| invalid("tar byte count overflow"))?;
        Ok(n)
    }
}
