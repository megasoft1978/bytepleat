use bytepleat::{
    archive::{self, ArchiveLimits},
    DecodeOptions, EncodeOptions, Format,
};
use std::{
    fs,
    io::Cursor,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

fn temp() -> PathBuf {
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let p = std::env::temp_dir().join(format!(
        "bytepleat-archive-test-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos()
            + NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed) as u128
    ));
    fs::create_dir(&p).unwrap();
    p
}
fn opts() -> EncodeOptions {
    EncodeOptions {
        format: Format::Gzip,
        ..EncodeOptions::default()
    }
}

fn gzip_tar(entries: Vec<(&str, tar::EntryType, &[u8])>) -> Vec<u8> {
    let mut compressed = Vec::new();
    {
        let encoder =
            flate2::write::GzEncoder::new(&mut compressed, flate2::Compression::default());
        let mut builder = tar::Builder::new(encoder);
        for (name, kind, data) in entries {
            let mut h = tar::Header::new_ustar();
            h.set_entry_type(kind);
            h.set_size(data.len() as u64);
            h.set_mode(0o644);
            let raw = h.as_mut_bytes();
            raw[..name.len()].copy_from_slice(name.as_bytes());
            h.set_cksum();
            builder.append(&h, data).unwrap();
        }
        let encoder = builder.into_inner().unwrap();
        encoder.finish().unwrap();
    }
    compressed
}

#[test]
fn limits_have_plan_defaults_and_pco_is_rejected() {
    let l = ArchiveLimits::default();
    assert_eq!(
        (
            l.max_entries,
            l.max_total_bytes,
            l.max_depth,
            l.deterministic
        ),
        (100_000, 1_073_741_824, 64, false)
    );
    let root = temp();
    let pco = EncodeOptions {
        format: Format::Pco,
        ..opts()
    };
    assert!(archive::pack(&root, Vec::new(), &pco, &l).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn pack_preflight_enforces_entry_and_byte_limits() {
    let root = temp();
    fs::write(root.join("a"), b"12345").unwrap();
    let mut l = ArchiveLimits {
        max_entries: 0,
        ..ArchiveLimits::default()
    };
    assert!(archive::pack(&root, Vec::new(), &opts(), &l).is_err());
    l.max_entries = 2;
    l.max_total_bytes = 4;
    assert!(archive::pack(&root, Vec::new(), &opts(), &l).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn round_trip_preserves_files_and_empty_directories() {
    let parent = temp();
    let root = parent.join("source");
    fs::create_dir_all(root.join("empty")).unwrap();
    fs::create_dir_all(root.join("nested")).unwrap();
    fs::write(root.join("nested/data.bin"), [0, 255, 1, 2, 3]).unwrap();
    let mut bytes = Vec::new();
    archive::pack(&root, &mut bytes, &opts(), &ArchiveLimits::default()).unwrap();
    let dest = parent.join("restored");
    archive::unpack(
        Cursor::new(bytes),
        &dest,
        &DecodeOptions::default(),
        &ArchiveLimits::default(),
    )
    .unwrap();
    assert_eq!(
        fs::read(dest.join("nested/data.bin")).unwrap(),
        [0, 255, 1, 2, 3]
    );
    assert!(dest.join("empty").is_dir());
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn unicode_and_gnu_long_names_round_trip() {
    let parent = temp();
    let root = parent.join("source");
    let long = format!(
        "{}/payload.bin",
        (0..5)
            .map(|_| "segment-with-a-long-name")
            .collect::<Vec<_>>()
            .join("/")
    );
    fs::create_dir_all(root.join("café")).unwrap();
    fs::write(root.join("café/данные.txt"), b"utf8").unwrap();
    fs::create_dir_all(root.join(long.rsplit_once('/').unwrap().0)).unwrap();
    fs::write(root.join(&long), b"long").unwrap();
    let mut bytes = Vec::new();
    archive::pack(&root, &mut bytes, &opts(), &ArchiveLimits::default()).unwrap();
    let dest = parent.join("restored");
    archive::unpack(
        Cursor::new(bytes),
        &dest,
        &DecodeOptions::default(),
        &ArchiveLimits::default(),
    )
    .unwrap();
    assert_eq!(fs::read(dest.join("café/данные.txt")).unwrap(), b"utf8");
    assert_eq!(fs::read(dest.join(long)).unwrap(), b"long");
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn canonical_unicode_aliases_are_rejected_before_publication() {
    let parent = temp();
    // Construct raw archive names: many host filesystems normalize these on
    // creation, so the fixture must not depend on two distinct disk names.
    let tar = gzip_tar(vec![
        ("caf\u{e9}", tar::EntryType::Regular, b"a"),
        ("cafe\u{301}", tar::EntryType::Regular, b"b"),
    ]);
    let dest = parent.join("restored");
    assert!(archive::unpack(
        Cursor::new(tar),
        &dest,
        &DecodeOptions::default(),
        &ArchiveLimits::default()
    )
    .is_err());
    assert!(!dest.exists());
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn local_pax_path_is_bounded_and_size_override_is_rejected() {
    let parent = temp();
    let pax = gzip_tar(vec![
        (
            "PaxHeaders/file",
            tar::EntryType::XHeader,
            b"16 path=renamed\n",
        ),
        ("file", tar::EntryType::Regular, b"data"),
    ]);
    let dest = parent.join("pax");
    archive::unpack(
        Cursor::new(pax),
        &dest,
        &DecodeOptions::default(),
        &ArchiveLimits::default(),
    )
    .unwrap();
    assert_eq!(fs::read(dest.join("renamed")).unwrap(), b"data");

    let oversized = vec![b'x'; 128 * 1024];
    let too_big = gzip_tar(vec![(
        "PaxHeaders/file",
        tar::EntryType::XHeader,
        &oversized,
    )]);
    let rejected = parent.join("oversized");
    assert!(archive::unpack(
        Cursor::new(too_big),
        &rejected,
        &DecodeOptions::default(),
        &ArchiveLimits::default()
    )
    .is_err());
    assert!(!rejected.exists());

    let mismatch = gzip_tar(vec![
        ("PaxHeaders/file", tar::EntryType::XHeader, b"11 size=99\n"),
        ("file", tar::EntryType::Regular, b"data"),
    ]);
    let rejected = parent.join("size");
    assert!(archive::unpack(
        Cursor::new(mismatch),
        &rejected,
        &DecodeOptions::default(),
        &ArchiveLimits::default()
    )
    .is_err());
    assert!(!rejected.exists());
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn unpack_refuses_existing_destination_without_changing_it() {
    let parent = temp();
    let dest = parent.join("existing");
    fs::create_dir(&dest).unwrap();
    fs::write(dest.join("keep"), b"same").unwrap();
    assert!(archive::unpack(
        Cursor::new([]),
        &dest,
        &DecodeOptions::default(),
        &ArchiveLimits::default()
    )
    .is_err());
    assert_eq!(fs::read(dest.join("keep")).unwrap(), b"same");
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn unpack_rejects_traversal_links_and_limits_without_publishing() {
    let parent = temp();
    let limits = ArchiveLimits::default();
    let traversal = gzip_tar(vec![("../outside", tar::EntryType::Regular, b"x")]);
    let dest = parent.join("traversal");
    assert!(archive::unpack(
        Cursor::new(traversal),
        &dest,
        &DecodeOptions::default(),
        &limits
    )
    .is_err());
    assert!(!dest.exists());

    let link = gzip_tar(vec![("link", tar::EntryType::Symlink, b"")]);
    let dest = parent.join("link");
    assert!(archive::unpack(Cursor::new(link), &dest, &DecodeOptions::default(), &limits).is_err());
    assert!(!dest.exists());

    let deep = gzip_tar(vec![("a/b/c", tar::EntryType::Regular, b"x")]);
    let dest = parent.join("deep");
    let mut shallow = limits.clone();
    shallow.max_depth = 2;
    assert!(archive::unpack(
        Cursor::new(deep),
        &dest,
        &DecodeOptions::default(),
        &shallow
    )
    .is_err());
    assert!(!dest.exists());
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn accepts_dot_prefix_aliases_but_rejects_duplicate_and_appended_payload() {
    let parent = temp();
    let dot = gzip_tar(vec![("./file", tar::EntryType::Regular, b"ok")]);
    let dest = parent.join("dot");
    archive::unpack(
        Cursor::new(dot),
        &dest,
        &DecodeOptions::default(),
        &ArchiveLimits::default(),
    )
    .unwrap();
    assert_eq!(fs::read(dest.join("file")).unwrap(), b"ok");

    let duplicate = gzip_tar(vec![
        ("./file", tar::EntryType::Regular, b"a"),
        ("file", tar::EntryType::Regular, b"b"),
    ]);
    let dest2 = parent.join("duplicate");
    assert!(archive::unpack(
        Cursor::new(duplicate),
        &dest2,
        &DecodeOptions::default(),
        &ArchiveLimits::default()
    )
    .is_err());
    assert!(!dest2.exists());

    let mut appended = gzip_tar(vec![("file", tar::EntryType::Regular, b"ok")]);
    appended.extend(gzip_tar(vec![("hidden", tar::EntryType::Regular, b"bad")]));
    let dest3 = parent.join("appended");
    assert!(archive::unpack(
        Cursor::new(appended),
        &dest3,
        &DecodeOptions::default(),
        &ArchiveLimits::default()
    )
    .is_err());
    assert!(!dest3.exists());
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn rejects_missing_tar_end_marker() {
    let td = tempfile::tempdir().unwrap();
    let mut builder = tar::Builder::new(Vec::new());
    let mut header = tar::Header::new_gnu();
    header.set_size(1);
    header.set_mode(0o644);
    header.set_cksum();
    builder
        .append_data(&mut header, "file", std::io::Cursor::new(b"x"))
        .unwrap();
    let raw = builder.into_inner().unwrap();
    let mut encoded = Vec::new();
    bytepleat::codecs::compress(
        std::io::Cursor::new(&raw[..1024]),
        &mut encoded,
        &bytepleat::EncodeOptions::default(),
    )
    .unwrap();
    let dest = td.path().join("output");
    assert!(bytepleat::archive::unpack(
        std::io::Cursor::new(encoded),
        &dest,
        &bytepleat::DecodeOptions::default(),
        &bytepleat::archive::ArchiveLimits::default()
    )
    .is_err());
    assert!(!dest.exists());
}
