use crate::Stats;
use same_file::is_same_file;
use std::{
    fs::{self, File},
    io::{self, Write},
    path::Path,
};
use tempfile::NamedTempFile;

/// Interrupt cleanup for the staging file (Unix only).
///
/// While a staged output exists, SIGINT/SIGTERM/SIGHUP unlink it and then
/// re-raise the signal with the default action, so the process still dies
/// "by signal" (non-zero status, e.g. 130 for SIGINT in shells). Only
/// async-signal-safe calls (`unlink`, `signal`, `raise`) run in the handler.
/// No dependency is used; the libc symbols are declared directly. SIGKILL
/// cannot be caught, and Windows has no handler (the staging file may remain).
#[cfg(unix)]
mod interrupt {
    use std::{
        ffi::{c_char, c_int, CString},
        os::unix::ffi::OsStrExt,
        path::Path,
        sync::{
            atomic::{AtomicPtr, Ordering},
            Once,
        },
    };
    extern "C" {
        fn signal(sig: c_int, handler: usize) -> usize;
        fn raise(sig: c_int) -> c_int;
        fn unlink(path: *const c_char) -> c_int;
    }
    static STAGED: AtomicPtr<c_char> = AtomicPtr::new(std::ptr::null_mut());
    static INSTALL: Once = Once::new();

    extern "C" fn on_signal(sig: c_int) {
        let p = STAGED.swap(std::ptr::null_mut(), Ordering::SeqCst);
        // SAFETY: `p` is a leaked, NUL-terminated CString (or null); the calls
        // below are async-signal-safe. SIG_DFL is 0.
        unsafe {
            if !p.is_null() {
                unlink(p);
            }
            signal(sig, 0);
            raise(sig);
        }
    }
    pub fn arm(path: &Path) {
        INSTALL.call_once(|| {
            for sig in [1, 2, 15] {
                // SAFETY: installing a handler that only uses async-signal-safe calls.
                unsafe { signal(sig, on_signal as extern "C" fn(c_int) as usize) };
            }
        });
        if let Ok(c) = CString::new(path.as_os_str().as_bytes()) {
            // Leaked on purpose: the handler may read it at any time.
            STAGED.store(c.into_raw(), Ordering::SeqCst);
        }
    }
    /// Stop the handler from touching the path (call before persist).
    pub fn disarm() {
        STAGED.swap(std::ptr::null_mut(), Ordering::SeqCst);
    }
}
#[cfg(not(unix))]
mod interrupt {
    pub fn arm(_: &std::path::Path) {}
    pub fn disarm() {}
}

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
    interrupt::arm(temp.path());
    let staged: io::Result<Stats> = (|| {
        let stats = write(temp.as_file_mut())?;
        temp.as_file_mut().flush()?;
        temp.as_file().sync_all()?;
        Ok(stats)
    })();
    interrupt::disarm();
    let stats = staged?;
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
