use bytepleat::{
    archive::ArchiveLimits,
    archive_safety::ReadLimits,
    archive_zip::{self, PackOptions},
};
use std::{fs, io::Cursor};
use tempfile::tempdir;
use zip::{write::SimpleFileOptions, CompressionMethod, ZipWriter};

fn limits() -> ReadLimits {
    ReadLimits::default()
}
fn pack(src: &std::path::Path, path: &std::path::Path, stored: bool) {
    let mut f = fs::File::create(path).unwrap();
    archive_zip::pack(
        src,
        &mut f,
        &PackOptions { level: 6, stored },
        &ArchiveLimits::default(),
    )
    .unwrap();
}
#[test]
fn stored_and_deflate_file_and_tree_roundtrip() {
    let t = tempdir().unwrap();
    let src = t.path().join("src");
    fs::create_dir(&src).unwrap();
    fs::create_dir(src.join("empty")).unwrap();
    fs::write(
        src.join("é-long-名前-abcdefghijklmnopqrstuvwxyz.txt"),
        b"byte data\0\xff",
    )
    .unwrap();
    for stored in [true, false] {
        let z = t.path().join(format!("{stored}.zip"));
        pack(&src, &z, stored);
        let dst = t.path().join(format!("out-{stored}"));
        let s = archive_zip::unpack(&z, &dst, &limits()).unwrap();
        assert_eq!(
            fs::read(dst.join("é-long-名前-abcdefghijklmnopqrstuvwxyz.txt")).unwrap(),
            b"byte data\0\xff"
        );
        assert!(dst.join("empty").is_dir());
        assert_eq!(s.output_bytes, 11);
        assert_eq!(archive_zip::test(&z, &limits()).unwrap().output_bytes, 11);
    }
}
fn raw_zip(name: &str, mode: Option<u32>) -> Vec<u8> {
    let c = Cursor::new(Vec::new());
    let mut z = ZipWriter::new(c);
    let mut o = SimpleFileOptions::default().compression_method(CompressionMethod::Stored);
    if let Some(m) = mode {
        o = o.unix_permissions(m)
    }
    z.start_file(name, o).unwrap();
    use std::io::Write;
    z.write_all(b"x").unwrap();
    z.finish().unwrap().into_inner()
}
#[test]
fn rejects_traversal_and_links() {
    let t = tempdir().unwrap();
    for (name, mode) in [("../escape", None), ("/absolute", None)] {
        let p = t.path().join("bad.zip");
        fs::write(&p, raw_zip(name, mode)).unwrap();
        assert!(archive_zip::test(&p, &limits()).is_err());
    }
}
#[test]
fn rejects_trailing_bytes_and_preserves_existing_destination() {
    let t = tempdir().unwrap();
    let src = t.path().join("f");
    fs::write(&src, b"ok").unwrap();
    let p = t.path().join("a.zip");
    pack(&src, &p, false);
    let mut b = fs::read(&p).unwrap();
    b.extend_from_slice(b"junk");
    fs::write(&p, &b).unwrap();
    assert!(archive_zip::test(&p, &limits()).is_err());
    let dest = t.path().join("existing");
    fs::create_dir(&dest).unwrap();
    fs::write(dest.join("keep"), b"yes").unwrap();
    assert!(archive_zip::unpack(&p, &dest, &limits()).is_err());
    assert_eq!(fs::read(dest.join("keep")).unwrap(), b"yes");
}
#[test]
fn rejects_malformed_eocd_and_zip64_markers() {
    let t = tempdir().unwrap();
    let p = t.path().join("bad.zip");
    for bytes in [
        b"PK\x05\x06\0\0\0\0\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\0\0".to_vec(),
        b"PK\x05\x06\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0".to_vec(),
    ] {
        fs::write(&p, bytes).unwrap();
        assert!(archive_zip::test(&p, &limits()).is_err());
    }
}

#[test]
fn rejects_case_and_nfc_collisions_before_decoding() {
    let t = tempdir().unwrap();
    let p = t.path().join("collision.zip");
    let mut z = ZipWriter::new(Cursor::new(Vec::new()));
    for name in ["A.txt", "a.TXT"] {
        z.start_file(name, SimpleFileOptions::default()).unwrap();
        use std::io::Write;
        z.write_all(b"x").unwrap();
    }
    fs::write(&p, z.finish().unwrap().into_inner()).unwrap();
    assert!(archive_zip::test(&p, &limits()).is_err());
}

#[test]
fn crc_tamper_and_truncation_fail() {
    let t = tempdir().unwrap();
    let source = t.path().join("file");
    fs::write(&source, b"payload").unwrap();
    let p = t.path().join("x.zip");
    pack(&source, &p, true);
    let original = fs::read(&p).unwrap();
    let mut corrupt = original.clone();
    let data = 30
        + u16::from_le_bytes([corrupt[26], corrupt[27]]) as usize
        + u16::from_le_bytes([corrupt[28], corrupt[29]]) as usize;
    corrupt[data] ^= 0x20;
    fs::write(&p, corrupt).unwrap();
    assert!(archive_zip::test(&p, &limits()).is_err());
    fs::write(&p, &original[..original.len() - 8]).unwrap();
    assert!(archive_zip::test(&p, &limits()).is_err());
}

#[test]
fn applies_output_entry_and_header_caps() {
    let t = tempdir().unwrap();
    let source = t.path().join("large");
    fs::write(&source, vec![7; 128]).unwrap();
    let p = t.path().join("x.zip");
    pack(&source, &p, false);
    let mut l = limits();
    l.archive.max_total_bytes = 64;
    assert!(archive_zip::test(&p, &l).is_err());
    let mut l = limits();
    l.archive.max_entries = 0;
    assert!(archive_zip::test(&p, &l).is_err());
    let mut l = limits();
    l.max_header_bytes = 1;
    assert!(archive_zip::test(&p, &l).is_err());
}

#[test]
fn rejects_local_zip64_and_unreferenced_prefix_payload() {
    let t = tempdir().unwrap();
    let p = t.path().join("bad.zip");
    let original = raw_zip("ok", None);
    let mut prefixed = b"hidden".to_vec();
    prefixed.extend_from_slice(&original);
    fs::write(&p, prefixed).unwrap();
    assert!(archive_zip::test(&p, &limits()).is_err());
    let mut changed = original;
    changed[26] = 3; // central/local names disagree
    fs::write(&p, changed).unwrap();
    assert!(archive_zip::test(&p, &limits()).is_err());
}

#[test]
fn exact_duplicate_names_cannot_be_silently_dropped() {
    use std::io::Write;
    let t = tempdir().unwrap();
    let p = t.path().join("duplicate.zip");
    let mut writer = ZipWriter::new(Cursor::new(Vec::new()));
    for name in ["one", "two"] {
        writer
            .start_file(
                name,
                SimpleFileOptions::default().compression_method(CompressionMethod::Stored),
            )
            .unwrap();
        writer.write_all(b"data").unwrap();
    }
    let mut data = writer.finish().unwrap().into_inner();
    for at in 0..data.len() - 2 {
        if &data[at..at + 3] == b"two" {
            data[at..at + 3].copy_from_slice(b"one");
        }
    }
    fs::write(&p, data).unwrap();
    assert!(archive_zip::test(&p, &limits()).is_err());
    assert!(archive_zip::info(&p, &limits()).is_err());
    let destination = t.path().join("out");
    assert!(archive_zip::unpack(&p, &destination, &limits()).is_err());
    assert!(!destination.exists());
}

fn dotted_zip(entries: &[(&str, bool)]) -> Vec<u8> {
    use std::io::Write;
    let mut z = ZipWriter::new(Cursor::new(Vec::new()));
    let o = SimpleFileOptions::default().compression_method(CompressionMethod::Stored);
    for (name, dir) in entries {
        if *dir {
            z.add_directory(*name, o).unwrap();
        } else {
            z.start_file(*name, o).unwrap();
            z.write_all(b"x").unwrap();
        }
    }
    z.finish().unwrap().into_inner()
}
#[test]
fn bsdtar_style_dot_root_extracts() {
    let t = tempdir().unwrap();
    let z = t.path().join("dot.zip");
    fs::write(
        &z,
        dotted_zip(&[
            ("./", true),
            ("./dir/", true),
            ("./top.txt", false),
            ("./dir/file", false),
        ]),
    )
    .unwrap();
    let dst = t.path().join("out");
    let s = archive_zip::unpack(&z, &dst, &limits()).unwrap();
    assert_eq!(s.output_bytes, 2);
    assert!(dst.join("dir").is_dir());
    assert_eq!(fs::read(dst.join("top.txt")).unwrap(), b"x");
    assert_eq!(fs::read(dst.join("dir/file")).unwrap(), b"x");
    assert_eq!(archive_zip::test(&z, &limits()).unwrap().output_bytes, 2);
}
#[test]
fn dot_root_does_not_weaken_path_checks() {
    let t = tempdir().unwrap();
    let cases: &[&[(&str, bool)]] = &[
        &[("./", true), ("../evil", false)],
        &[("./", true), ("./../evil", false)],
        &[("./", true), ("/abs", false)],
        &[("./", true), ("a\\b", false)],
        &[("./", true), ("C:/x", false)],
        &[("././", true)],
        &[("./", true), (".//x", false)],
        &[("./", true), ("./a/", true), ("A", false)],
    ];
    for (i, c) in cases.iter().enumerate() {
        let z = t.path().join(format!("{i}.zip"));
        fs::write(&z, dotted_zip(c)).unwrap();
        let dst = t.path().join(format!("o{i}"));
        assert!(
            archive_zip::unpack(&z, &dst, &limits()).is_err(),
            "case {i}"
        );
        assert!(!t.path().join("evil").exists());
    }
}

/// Hand-built ZIP of stored directory entries. The zip crate's writer refuses
/// duplicate names, so duplicates are emitted byte by byte here.
fn hand_dir_zip(names: &[&str]) -> Vec<u8> {
    let mut out = Vec::new();
    let mut central = Vec::new();
    for name in names {
        let n = name.as_bytes();
        let offset = out.len() as u32;
        // Local file header: version 2.0, stored, no payload, DOS date 1980-01-01.
        out.extend_from_slice(&[0x50, 0x4b, 0x03, 0x04]);
        out.extend_from_slice(&20u16.to_le_bytes());
        out.extend_from_slice(&0u16.to_le_bytes());
        out.extend_from_slice(&0u16.to_le_bytes());
        out.extend_from_slice(&0u16.to_le_bytes());
        out.extend_from_slice(&0x21u16.to_le_bytes());
        out.extend_from_slice(&[0; 12]);
        out.extend_from_slice(&(n.len() as u16).to_le_bytes());
        out.extend_from_slice(&0u16.to_le_bytes());
        out.extend_from_slice(n);
        // Central directory record: made by unix 3.0, unix dir mode 0755 plus DOS dir bit.
        central.extend_from_slice(&[0x50, 0x4b, 0x01, 0x02]);
        central.extend_from_slice(&0x031eu16.to_le_bytes());
        central.extend_from_slice(&20u16.to_le_bytes());
        central.extend_from_slice(&0u16.to_le_bytes());
        central.extend_from_slice(&0u16.to_le_bytes());
        central.extend_from_slice(&0u16.to_le_bytes());
        central.extend_from_slice(&0x21u16.to_le_bytes());
        central.extend_from_slice(&[0; 12]);
        central.extend_from_slice(&(n.len() as u16).to_le_bytes());
        central.extend_from_slice(&0u16.to_le_bytes());
        central.extend_from_slice(&0u16.to_le_bytes());
        central.extend_from_slice(&0u16.to_le_bytes());
        central.extend_from_slice(&0u16.to_le_bytes());
        central.extend_from_slice(&((0o040755u32 << 16) | 0x10).to_le_bytes());
        central.extend_from_slice(&offset.to_le_bytes());
        central.extend_from_slice(n);
    }
    let cd_offset = out.len() as u32;
    let cd_size = central.len() as u32;
    out.extend_from_slice(&central);
    // End of central directory record, no comment.
    out.extend_from_slice(&[0x50, 0x4b, 0x05, 0x06, 0, 0, 0, 0]);
    out.extend_from_slice(&(names.len() as u16).to_le_bytes());
    out.extend_from_slice(&(names.len() as u16).to_le_bytes());
    out.extend_from_slice(&cd_size.to_le_bytes());
    out.extend_from_slice(&cd_offset.to_le_bytes());
    out.extend_from_slice(&0u16.to_le_bytes());
    out
}
#[test]
fn duplicate_dot_root_is_rejected_and_single_dot_root_extracts() {
    let t = tempdir().unwrap();
    let dup = t.path().join("dup.zip");
    fs::write(&dup, hand_dir_zip(&["./", "./"])).unwrap();
    let err = archive_zip::test(&dup, &limits()).unwrap_err();
    assert!(
        err.to_string()
            .contains("ZIP duplicate names or metadata index mismatch"),
        "unexpected error: {err}"
    );
    let dst = t.path().join("dup-out");
    assert!(archive_zip::unpack(&dup, &dst, &limits()).is_err());
    assert!(!dst.exists());

    let good = t.path().join("good.zip");
    fs::write(&good, hand_dir_zip(&["./", "dir/"])).unwrap();
    let dst = t.path().join("good-out");
    archive_zip::unpack(&good, &dst, &limits()).unwrap();
    assert!(dst.join("dir").is_dir());
    assert_eq!(archive_zip::test(&good, &limits()).unwrap().output_bytes, 0);
}
