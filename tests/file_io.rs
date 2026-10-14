use arqlet::{file_io::atomic_output, Stats};
use std::{
    fs,
    io::{self, Write},
    path::Path,
};
use tempfile::tempdir;

fn write(path: &Path, input: Option<&Path>, force: bool, bytes: &[u8]) -> io::Result<Stats> {
    atomic_output(path, input, force, |f| {
        f.write_all(bytes)?;
        Ok(Stats {
            input_bytes: bytes.len() as u64,
            output_bytes: bytes.len() as u64,
        })
    })
}
#[test]
fn atomic_failure_and_no_clobber_preserve_existing() {
    let d = tempdir().unwrap();
    let target = d.path().join("out");
    fs::write(&target, b"original").unwrap();
    assert!(write(&target, None, false, b"new").is_err());
    assert_eq!(fs::read(&target).unwrap(), b"original");
    let result = atomic_output(&target, None, true, |f| {
        f.write_all(b"partial")?;
        Err(io::Error::other("failure"))
    });
    assert!(result.is_err());
    assert_eq!(fs::read(&target).unwrap(), b"original");
}
#[test]
fn rejects_alias_and_symlink() {
    let d = tempdir().unwrap();
    let src = d.path().join("src");
    fs::write(&src, b"source").unwrap();
    assert!(write(&src, Some(&src), true, b"bad").is_err());
    #[cfg(unix)]
    {
        let link = d.path().join("link");
        std::os::unix::fs::symlink(&src, &link).unwrap();
        assert!(write(&link, None, true, b"bad").is_err());
    }
    #[cfg(unix)]
    {
        let hard = d.path().join("hard");
        std::fs::hard_link(&src, &hard).unwrap();
        assert!(write(&hard, Some(&src), true, b"bad").is_err());
    }
    assert_eq!(fs::read(&src).unwrap(), b"source");
}
