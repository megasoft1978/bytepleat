use crate::Stats;
use same_file::is_same_file;
use std::{
    fs::{self, File},
    io::{self, Write},
    path::Path,
};
use tempfile::NamedTempFile;

pub fn atomic_output(
    path: &Path,
    input: Option<&Path>,
    force: bool,
    write: impl FnOnce(&mut File) -> io::Result<Stats>,
) -> io::Result<Stats> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let name = path.file_name().ok_or_else(|| {
        io::Error::new(io::ErrorKind::InvalidInput, "output path has no filename")
    })?;
    if let Some(src) = input {
        let exists = |p: &Path| match fs::symlink_metadata(p) {
            Ok(_) => Ok(true),
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(false),
            Err(e) => Err(e),
        };
        let src_exists = exists(src)?;
        let out_exists = exists(path)?;
        if src_exists && out_exists && is_same_file(src, path)? {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "input and output refer to the same file",
            ));
        }
    }
    match fs::symlink_metadata(path) {
        Ok(meta) => {
            if meta.file_type().is_symlink() || !meta.is_file() {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "output must be a regular file, not a link or directory",
                ));
            }
            if !force {
                return Err(io::Error::new(
                    io::ErrorKind::AlreadyExists,
                    "output already exists (use force to replace it)",
                ));
            }
        }
        Err(e) if e.kind() == io::ErrorKind::NotFound => {}
        Err(e) => return Err(e),
    }
    let mut temp = NamedTempFile::new_in(parent)?;
    let stats = write(temp.as_file_mut())?;
    temp.as_file_mut().flush()?;
    temp.as_file().sync_all()?;
    if force {
        temp.persist(path).map_err(|e| e.error)?;
    } else {
        temp.persist_noclobber(path).map_err(|e| e.error)?;
    }
    if let Ok(dir) = File::open(parent) {
        let _ = dir.sync_all();
    }
    let _ = name;
    Ok(stats)
}
