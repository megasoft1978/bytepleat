use std::{
    io::Write,
    process::{Command, Stdio},
};
#[test]
fn explicit_stdout_and_archive_pipeline() {
    let td = tempfile::tempdir().unwrap();
    let exe = env!("CARGO_BIN_EXE_arqlet");
    let payload = b"binary\0pipeline";
    for format in ["zstd", "gzip", "lz4"] {
        let mut child = Command::new(exe)
            .current_dir(td.path())
            .args(["compress", "-", "-o", "-", "--format", format, "--quiet"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();
        child.stdin.take().unwrap().write_all(payload).unwrap();
        let packed = child.wait_with_output().unwrap();
        assert!(packed.status.success());
        assert!(!packed.stdout.is_empty());
        let mut child = Command::new(exe)
            .current_dir(td.path())
            .args(["decompress", "-", "-o", "-", "--quiet"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(&packed.stdout)
            .unwrap();
        let restored = child.wait_with_output().unwrap();
        assert!(restored.status.success());
        assert_eq!(restored.stdout, payload);
        assert!(!td.path().join("-").exists());
    }
    std::fs::create_dir(td.path().join("tree")).unwrap();
    std::fs::write(td.path().join("tree/f"), payload).unwrap();
    let tar = Command::new(exe)
        .current_dir(td.path())
        .args(["pack", "tree", "-o", "-", "--quiet"])
        .output()
        .unwrap();
    assert!(tar.status.success());
    assert!(!tar.stdout.is_empty());
    assert!(!td.path().join("-").exists());
}
