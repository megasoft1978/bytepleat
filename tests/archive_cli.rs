use std::{
    fs,
    io::Write,
    process::{Command, Stdio},
};
#[test]
fn zip_sevenz_named_file_and_pipe_workflows_preserve_bytes() {
    let t = tempfile::tempdir().unwrap();
    let source = t.path().join("input.bin");
    fs::write(&source, b"bytes\0\xffbytes").unwrap();
    let cli = env!("CARGO_BIN_EXE_arqlet");
    for format in ["zip", "7z"] {
        let output = Command::new(cli)
            .args([
                "pack",
                source.to_str().unwrap(),
                "--format",
                format,
                "-o",
                "-",
            ])
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        let destination = t.path().join(format);
        let mut p = Command::new(cli)
            .args(["unpack", "-", "-o", destination.to_str().unwrap()])
            .stdin(Stdio::piped())
            .spawn()
            .unwrap();
        p.stdin.take().unwrap().write_all(&output.stdout).unwrap();
        assert!(p.wait().unwrap().success());
        assert_eq!(
            fs::read(destination.join("input.bin")).unwrap(),
            fs::read(&source).unwrap()
        );
        let archive = t.path().join(format!("file.{format}"));
        fs::write(&archive, &output.stdout).unwrap();
        assert!(Command::new(cli)
            .args(["test", archive.to_str().unwrap()])
            .status()
            .unwrap()
            .success());
        let info = Command::new(cli)
            .args(["info", archive.to_str().unwrap(), "--json"])
            .output()
            .unwrap();
        assert!(info.status.success());
        let value: serde_json::Value = serde_json::from_slice(&info.stdout).unwrap();
        assert_eq!(value["integrity_validated"], false);
        let before = fs::read(&archive).unwrap();
        assert!(!Command::new(cli)
            .args([
                "pack",
                source.to_str().unwrap(),
                "--format",
                format,
                "-o",
                archive.to_str().unwrap()
            ])
            .status()
            .unwrap()
            .success());
        assert_eq!(fs::read(&archive).unwrap(), before);
    }
}
