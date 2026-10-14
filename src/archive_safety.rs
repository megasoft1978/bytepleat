//! Shared filesystem policy for standard ZIP and 7z adapters.
use crate::{archive::ArchiveLimits, invalid};
use std::{
    collections::{HashMap, HashSet},
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    path::{Component, Path, PathBuf},
};
use unicode_normalization::UnicodeNormalization;
use walkdir::WalkDir;

#[derive(Clone, Debug)]
pub struct SourceItem {
    pub path: PathBuf,
    pub name: String,
    pub is_dir: bool,
    pub size: u64,
}
#[derive(Clone, Debug)]
pub struct ReadLimits {
    pub archive: ArchiveLimits,
    pub max_dictionary_bytes: u64,
    pub max_header_bytes: u64,
    pub max_compressed_bytes: u64,
}
impl Default for ReadLimits {
    fn default() -> Self {
        Self {
            archive: ArchiveLimits::default(),
            max_dictionary_bytes: 128 * 1024 * 1024,
            max_header_bytes: 16 * 1024 * 1024,
            max_compressed_bytes: 1024 * 1024 * 1024,
        }
    }
}
fn component(s: &str) -> bool {
    if s.is_empty()
        || s == "."
        || s == ".."
        || s.ends_with(['.', ' '])
        || s.contains(['\\', ':', '\0'])
        || s.chars().any(char::is_control)
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
pub fn normalize_name(raw: &str, is_dir: bool) -> io::Result<String> {
    if raw.len() > 4096 || raw.starts_with('/') || raw.contains(['\\', ':', '\0']) {
        return Err(invalid("unsafe or oversized archive path"));
    }
    let name = if is_dir {
        raw.strip_suffix('/').unwrap_or(raw)
    } else {
        raw
    };
    let mut names = Vec::new();
    for part in name.split('/') {
        if part == "." && names.is_empty() {
            continue;
        }
        if !component(part) {
            return Err(invalid("non-portable archive path component"));
        }
        names.push(part);
    }
    if names.is_empty() {
        return Err(invalid("empty archive path"));
    }
    Ok(names.join("/"))
}
fn key(s: &str) -> String {
    s.nfc().collect::<String>().to_lowercase().nfc().collect()
}
#[derive(Default)]
pub struct EntryPolicy {
    explicit: HashSet<String>,
    kinds: HashMap<String, (bool, String)>,
    count: u64,
    total: u64,
}
impl EntryPolicy {
    pub fn add(
        &mut self,
        raw: &str,
        is_dir: bool,
        size: u64,
        limits: &ArchiveLimits,
    ) -> io::Result<String> {
        let name = normalize_name(raw, is_dir)?;
        let pieces: Vec<_> = name.split('/').collect();
        if pieces.len() > limits.max_depth {
            return Err(invalid("archive depth limit exceeded"));
        }
        self.count = self
            .count
            .checked_add(1)
            .ok_or_else(|| invalid("entry count overflow"))?;
        if self.count > limits.max_entries {
            return Err(invalid("archive entry limit exceeded"));
        }
        if is_dir && size != 0 {
            return Err(invalid("directory carries data"));
        }
        self.total = self
            .total
            .checked_add(size)
            .ok_or_else(|| invalid("archive byte count overflow"))?;
        if self.total > limits.max_total_bytes {
            return Err(invalid("archive output limit exceeded"));
        }
        let mut prefix = String::new();
        for (i, part) in pieces.iter().enumerate() {
            if i > 0 {
                prefix.push('/');
            }
            prefix.push_str(part);
            let folded = key(&prefix);
            let dir = i + 1 < pieces.len() || is_dir;
            if let Some((prior_dir, prior_name)) = self.kinds.get(&folded) {
                if *prior_dir != dir || prior_name != &prefix {
                    return Err(invalid("archive path type or Unicode/case alias collision"));
                }
            } else {
                self.kinds.insert(folded.clone(), (dir, prefix.clone()));
            }
            if i + 1 == pieces.len() && !self.explicit.insert(folded) {
                return Err(invalid("duplicate archive entry"));
            }
        }
        Ok(name)
    }
    pub fn total_bytes(&self) -> u64 {
        self.total
    }
}
pub fn collect(source: &Path, limits: &ArchiveLimits) -> io::Result<Vec<SourceItem>> {
    let md = fs::symlink_metadata(source)?;
    if md.file_type().is_symlink() || !(md.is_dir() || md.is_file()) {
        return Err(invalid("archive input must be a regular file or directory"));
    }
    let mut items = Vec::new();
    let mut policy = EntryPolicy::default();
    if md.is_file() {
        let name = source
            .file_name()
            .and_then(|x| x.to_str())
            .ok_or_else(|| invalid("input name is not UTF-8"))?;
        let name = policy.add(name, false, md.len(), limits)?;
        items.push(SourceItem {
            path: source.to_path_buf(),
            name,
            is_dir: false,
            size: md.len(),
        });
    } else {
        for entry in WalkDir::new(source).follow_links(false).min_depth(1) {
            let e = entry.map_err(io::Error::other)?;
            let ty = e.file_type();
            if !(ty.is_dir() || ty.is_file()) {
                return Err(invalid("archive input contains a link or special entry"));
            }
            let rel = e.path().strip_prefix(source).map_err(io::Error::other)?;
            let mut parts = Vec::new();
            for c in rel.components() {
                match c {
                    Component::Normal(n) => parts.push(
                        n.to_str()
                            .ok_or_else(|| invalid("input path is not UTF-8"))?,
                    ),
                    _ => return Err(invalid("input escaped source root")),
                }
            }
            let size = if ty.is_file() {
                e.metadata().map_err(io::Error::other)?.len()
            } else {
                0
            };
            let name = policy.add(&parts.join("/"), ty.is_dir(), size, limits)?;
            items.push(SourceItem {
                path: e.path().to_path_buf(),
                name,
                is_dir: ty.is_dir(),
                size,
            });
        }
    }
    items.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(items)
}
pub fn stage(dest: &Path) -> io::Result<tempfile::TempDir> {
    match fs::symlink_metadata(dest) {
        Ok(_) => {
            return Err(io::Error::new(
                io::ErrorKind::AlreadyExists,
                "destination already exists",
            ))
        }
        Err(e) if e.kind() == io::ErrorKind::NotFound => {}
        Err(e) => return Err(e),
    }
    let parent = dest
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let md = fs::symlink_metadata(parent)?;
    if !md.is_dir() || md.file_type().is_symlink() {
        return Err(invalid("destination parent must be a real directory"));
    }
    tempfile::Builder::new()
        .prefix(".bytepleat-extract-")
        .tempdir_in(parent)
}
pub fn write_entry(
    stage: &Path,
    name: &str,
    is_dir: bool,
    size: u64,
    reader: &mut dyn Read,
) -> io::Result<()> {
    let path = stage.join(name);
    if is_dir {
        fs::create_dir_all(path)?;
        return Ok(());
    }
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut output = OpenOptions::new().write(true).create_new(true).open(path)?;
    let mut limited = (&mut *reader).take(size);
    let copied = io::copy(&mut limited, &mut output)?;
    if copied != size {
        return Err(invalid("truncated archive entry"));
    }
    // Probe through the original entry reader to finish its checksum and reject
    // a lying length before publication. No over-limit byte is written.
    let mut extra = [0];
    if reader.read(&mut extra)? != 0 {
        return Err(invalid("archive entry exceeds declared size"));
    }
    output.flush()?;
    Ok(())
}
pub fn publish(stage: &tempfile::TempDir, dest: &Path) -> io::Result<()> {
    publish_with(stage, dest, |_| Ok(()))
}

fn publish_with(
    stage: &tempfile::TempDir,
    dest: &Path,
    mut after_move: impl FnMut(&Path) -> io::Result<()>,
) -> io::Result<()> {
    fs::create_dir(dest)?;
    let mut moved = Vec::new();
    let result = (|| {
        for item in fs::read_dir(stage.path())? {
            let item = item?;
            let target = dest.join(item.file_name());
            fs::rename(item.path(), &target)?;
            moved.push(target.clone());
            after_move(&target)?;
        }
        Ok::<_, io::Error>(())
    })();
    if let Err(error) = result {
        return Err(rollback_publication(stage.path(), dest, moved, error));
    }
    Ok(())
}

pub(crate) fn rollback_publication(
    stage: &Path,
    dest: &Path,
    moved: Vec<PathBuf>,
    cause: io::Error,
) -> io::Error {
    let mut failures = Vec::new();
    for target in moved.into_iter().rev() {
        let Some(name) = target.file_name() else {
            failures.push(format!(
                "invalid tracked publication path {}",
                target.display()
            ));
            continue;
        };
        let original = stage.join(name);
        if let Err(err) = fs::rename(&target, &original) {
            failures.push(format!("could not restore {}: {err}", original.display()));
        }
    }
    if let Err(err) = fs::remove_dir(dest) {
        if err.kind() != io::ErrorKind::NotFound {
            failures.push(format!("could not remove empty destination: {err}"));
        }
    }
    if failures.is_empty() {
        cause
    } else {
        io::Error::new(
            cause.kind(),
            format!(
                "{cause}; rollback cleanup incomplete: {}",
                failures.join("; ")
            ),
        )
    }
}
pub fn regular_input(path: &Path, limit: u64) -> io::Result<File> {
    let md = fs::symlink_metadata(path)?;
    if !md.is_file() || md.file_type().is_symlink() {
        return Err(invalid("archive input must be a regular seekable file"));
    }
    if md.len() > limit {
        return Err(invalid("compressed archive exceeds input limit"));
    }
    File::open(path)
}

#[cfg(test)]
mod publication_tests {
    use super::*;

    #[test]
    fn publication_error_restores_mixed_moved_children_and_preserves_unrelated_data() {
        let parent = tempfile::tempdir().unwrap();
        let dest = parent.path().join("restored");
        fs::write(parent.path().join("unrelated.txt"), b"keep me").unwrap();
        let stage = tempfile::tempdir_in(parent.path()).unwrap();
        fs::create_dir_all(stage.path().join("nested/sub")).unwrap();
        fs::write(stage.path().join("nested/sub/file.bin"), b"inside").unwrap();
        fs::write(stage.path().join("alpha.bin"), b"alpha").unwrap();
        fs::create_dir_all(stage.path().join("other")).unwrap();
        fs::write(stage.path().join("other/data"), b"other").unwrap();
        fs::write(stage.path().join("remaining"), b"not moved").unwrap();

        // Fail after alpha and nested have both moved, regardless of directory
        // iteration order. The callback runs for a moved root child.
        let mut moved_file = false;
        let mut moved_directory = false;
        let error = publish_with(&stage, &dest, |target| {
            moved_file |= target.file_name().is_some_and(|name| name == "alpha.bin");
            moved_directory |= target.file_name().is_some_and(|name| name == "nested");
            if moved_file && moved_directory {
                Err(io::Error::other("injected publication failure"))
            } else {
                Ok(())
            }
        })
        .unwrap_err();

        assert!(moved_file && moved_directory);
        assert_eq!(error.to_string(), "injected publication failure");
        assert!(!dest.exists());
        assert_eq!(
            fs::read(parent.path().join("unrelated.txt")).unwrap(),
            b"keep me"
        );
        assert_eq!(
            fs::read(stage.path().join("nested/sub/file.bin")).unwrap(),
            b"inside"
        );
        assert_eq!(fs::read(stage.path().join("alpha.bin")).unwrap(), b"alpha");
        assert_eq!(fs::read(stage.path().join("other/data")).unwrap(), b"other");
        assert_eq!(
            fs::read(stage.path().join("remaining")).unwrap(),
            b"not moved"
        );
    }

    #[test]
    fn preexisting_destination_is_never_replaced_or_removed() {
        let parent = tempfile::tempdir().unwrap();
        let dest = parent.path().join("restored");
        fs::create_dir(&dest).unwrap();
        fs::write(dest.join("keep"), b"existing").unwrap();
        let stage = tempfile::tempdir_in(parent.path()).unwrap();
        fs::write(stage.path().join("entry"), b"staged").unwrap();

        let error = publish(&stage, &dest).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::AlreadyExists);
        assert_eq!(fs::read(dest.join("keep")).unwrap(), b"existing");
        assert_eq!(fs::read(stage.path().join("entry")).unwrap(), b"staged");
    }

    #[test]
    fn rollback_error_reports_original_failure_and_incomplete_cleanup() {
        let parent = tempfile::tempdir().unwrap();
        let stage = parent.path().join("stage");
        fs::create_dir(&stage).unwrap();
        fs::create_dir_all(stage.join("entry/child")).unwrap();
        let dest = parent.path().join("dest");
        fs::create_dir_all(dest.join("entry/child")).unwrap();
        fs::write(dest.join("entry/child/concurrent"), b"keep").unwrap();

        let error = rollback_publication(
            &stage,
            &dest,
            vec![dest.join("entry")],
            io::Error::other("injected publication failure"),
        );
        assert!(error.to_string().contains("injected publication failure"));
        assert!(error.to_string().contains("rollback cleanup incomplete"));
        assert_eq!(
            fs::read(dest.join("entry/child/concurrent")).unwrap(),
            b"keep"
        );
    }
}
