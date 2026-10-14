use std::{fs, process::Command};
use tempfile::tempdir;
fn cli() -> Command {
    Command::new(env!("CARGO_BIN_EXE_bytepleat"))
}
#[test]
fn roundtrip_formats_and_numeric() {
    let d = tempdir().unwrap();
    let src = d.path().join("input.bin");
    let data = (0..8192).map(|n| (n % 251) as u8).collect::<Vec<_>>();
    fs::write(&src, &data).unwrap();
    for f in ["zstd", "gzip", "lz4"] {
        let c = d.path().join(format!("x.{f}"));
        let o = d.path().join(format!("o.{f}"));
        assert!(cli()
            .args([
                "compress",
                src.to_str().unwrap(),
                "-o",
                c.to_str().unwrap(),
                "--format",
                f
            ])
            .status()
            .unwrap()
            .success());
        assert!(cli()
            .args(["test", c.to_str().unwrap()])
            .status()
            .unwrap()
            .success());
        assert!(cli()
            .args(["decompress", c.to_str().unwrap(), "-o", o.to_str().unwrap()])
            .status()
            .unwrap()
            .success());
        assert_eq!(fs::read(o).unwrap(), data)
    }
    let nums = [0x00, 0x00, 0x80, 0x3f, 0x01, 0x00, 0xc0, 0x7f];
    let n = d.path().join("nums");
    fs::write(&n, nums).unwrap();
    let p = d.path().join("nums.pco");
    let out = d.path().join("nums.out");
    assert!(cli()
        .args([
            "compress",
            n.to_str().unwrap(),
            "-o",
            p.to_str().unwrap(),
            "--format",
            "pco",
            "--type",
            "f32"
        ])
        .status()
        .unwrap()
        .success());
    assert!(cli()
        .args([
            "decompress",
            p.to_str().unwrap(),
            "-o",
            out.to_str().unwrap(),
            "--type",
            "f32"
        ])
        .status()
        .unwrap()
        .success());
    assert_eq!(fs::read(out).unwrap(), fs::read(n).unwrap());
}
#[test]
fn errors_limits_pack_and_stream() {
    let d = tempdir().unwrap();
    let root = d.path().join("tree");
    fs::create_dir(&root).unwrap();
    fs::write(root.join("a"), b"payload").unwrap();
    let arch = d.path().join("a.tar.gz");
    assert!(cli()
        .args([
            "pack",
            root.to_str().unwrap(),
            "-o",
            arch.to_str().unwrap(),
            "--format",
            "gzip"
        ])
        .status()
        .unwrap()
        .success());
    assert!(!root.join("tree.tar.gz").exists());
    let dest = d.path().join("out");
    assert!(cli()
        .args([
            "unpack",
            arch.to_str().unwrap(),
            "-o",
            dest.to_str().unwrap()
        ])
        .status()
        .unwrap()
        .success());
    assert_eq!(fs::read(dest.join("a")).unwrap(), b"payload");
    let packed_inside = root.join("bad.tar.gz");
    assert!(!cli()
        .args([
            "pack",
            root.to_str().unwrap(),
            "-o",
            packed_inside.to_str().unwrap()
        ])
        .status()
        .unwrap()
        .success());
    let existing = d.path().join("exists");
    fs::write(&existing, b"keep").unwrap();
    assert!(!cli()
        .args([
            "compress",
            root.join("a").to_str().unwrap(),
            "-o",
            existing.to_str().unwrap()
        ])
        .status()
        .unwrap()
        .success());
    assert_eq!(fs::read(existing).unwrap(), b"keep");
    assert!(!cli()
        .args([
            "compress",
            root.join("a").to_str().unwrap(),
            "--format",
            "lz4",
            "--level",
            "2"
        ])
        .status()
        .unwrap()
        .success());
    assert!(cli()
        .args(["compress", "-", "--format", "gzip"])
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::null())
        .spawn()
        .is_ok());
}
