use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output},
};
use tempfile::tempdir;
fn cli() -> Command {
    Command::new(env!("CARGO_BIN_EXE_bytepleat"))
}
fn s(p: &Path) -> &str {
    p.to_str().unwrap()
}
fn tree(d: &Path) -> PathBuf {
    let root = d.join("tree");
    fs::create_dir(&root).unwrap();
    fs::write(root.join("a.txt"), b"payload").unwrap();
    root
}
fn pack(args: &[&str]) -> Output {
    cli().arg("pack").args(args).output().unwrap()
}
fn assert_ok(out: &Output) {
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
}
fn assert_valid(path: &Path) {
    assert_ok(&cli().args(["test", s(path)]).output().unwrap());
}
#[test]
fn zip_extension_selects_zip_without_format() {
    let d = tempdir().unwrap();
    let root = tree(d.path());
    let out = d.path().join("x.zip");
    assert_ok(&pack(&[s(&root), "-o", s(&out)]));
    assert!(fs::read(&out).unwrap().starts_with(b"PK\x03\x04"));
    assert_valid(&out);
}
#[test]
fn explicit_zip_format_with_zip_extension_works() {
    let d = tempdir().unwrap();
    let root = tree(d.path());
    let out = d.path().join("x.zip");
    assert_ok(&pack(&[s(&root), "--format", "zip", "-o", s(&out)]));
    assert!(fs::read(&out).unwrap().starts_with(b"PK\x03\x04"));
    assert_valid(&out);
}
#[test]
fn tar_zst_output_matches_explicit_zstd() {
    let d = tempdir().unwrap();
    let root = tree(d.path());
    let implicit = d.path().join("implicit.tar.zst");
    let explicit = d.path().join("explicit.tar.zst");
    assert_ok(&pack(&[s(&root), "-o", s(&implicit)]));
    assert_ok(&pack(&[s(&root), "--format", "zstd", "-o", s(&explicit)]));
    assert_eq!(fs::read(&implicit).unwrap(), fs::read(&explicit).unwrap());
    assert_valid(&implicit);
    assert_ok(&pack(&[s(&root)]));
    assert_eq!(
        fs::read(d.path().join("tree.tar.zst")).unwrap(),
        fs::read(&explicit).unwrap()
    );
}
#[test]
fn conflicting_format_and_extension_fail_without_output() {
    let d = tempdir().unwrap();
    let root = tree(d.path());
    let zip = d.path().join("x.zip");
    let out = pack(&[s(&root), "--format", "zstd", "-o", s(&zip)]);
    assert!(!out.status.success());
    let err = String::from_utf8_lossy(&out.stderr);
    assert!(
        err.contains(&format!(
            "--format zstd conflicts with output name {} (a .zip file is a ZIP archive)",
            zip.display()
        )),
        "{err}"
    );
    assert!(!zip.exists());
    let tzst = d.path().join("x.tar.zst");
    let out = pack(&[s(&root), "--format", "zip", "-o", s(&tzst)]);
    assert!(!out.status.success());
    let err = String::from_utf8_lossy(&out.stderr);
    assert!(
        err.contains(&format!(
            "--format zip conflicts with output name {}",
            tzst.display()
        )),
        "{err}"
    );
    assert!(!tzst.exists());
}
#[test]
fn sevenz_extension_selects_7z() {
    let d = tempdir().unwrap();
    let root = tree(d.path());
    let out = d.path().join("x.7z");
    assert_ok(&pack(&[s(&root), "-o", s(&out)]));
    assert!(fs::read(&out).unwrap().starts_with(b"7z\xbc\xaf\x27\x1c"));
    assert_valid(&out);
}
#[test]
fn tar_extensions_select_their_codec() {
    let d = tempdir().unwrap();
    let root = tree(d.path());
    for (name, magic) in [
        ("a.tar.gz", &[0x1f, 0x8b][..]),
        ("b.tgz", &[0x1f, 0x8b][..]),
        ("c.tar.lz4", &[0x04, 0x22, 0x4d, 0x18][..]),
        ("d.tzst", &[0x28, 0xb5, 0x2f, 0xfd][..]),
    ] {
        let out = d.path().join(name);
        assert_ok(&pack(&[s(&root), "-o", s(&out)]));
        assert!(fs::read(&out).unwrap().starts_with(magic), "{name}");
        assert_valid(&out);
    }
}
#[test]
fn extension_match_is_case_insensitive() {
    let d = tempdir().unwrap();
    let root = tree(d.path());
    let zip = d.path().join("UP.ZIP");
    assert_ok(&pack(&[s(&root), "-o", s(&zip)]));
    assert!(fs::read(&zip).unwrap().starts_with(b"PK\x03\x04"));
    let sevenz = d.path().join("UP.7Z");
    assert_ok(&pack(&[s(&root), "-o", s(&sevenz)]));
    assert!(fs::read(&sevenz)
        .unwrap()
        .starts_with(b"7z\xbc\xaf\x27\x1c"));
    let tgz = d.path().join("UP.TAR.GZ");
    assert_ok(&pack(&[s(&root), "-o", s(&tgz)]));
    assert!(fs::read(&tgz).unwrap().starts_with(&[0x1f, 0x8b]));
    let mismatch = d.path().join("MIXED.ZIP");
    let out = pack(&[s(&root), "--format", "zstd", "-o", s(&mismatch)]);
    assert!(!out.status.success());
    assert!(String::from_utf8_lossy(&out.stderr).contains("conflicts with output name"));
    assert!(!mismatch.exists());
}
