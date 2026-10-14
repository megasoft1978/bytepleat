use bytepleat::{
    archive::ArchiveLimits,
    archive_safety::ReadLimits,
    archive_sevenz::{self, PackOptions},
};
use sevenz_rust2::{ArchiveEntry, ArchiveWriter};
use std::{
    fs,
    io::Cursor,
    path::{Path, PathBuf},
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

fn temp() -> PathBuf {
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let p = std::env::temp_dir().join(format!(
        "bytepleat-7z-test-{}-{}",
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
fn output(root: &Path, solid: bool) -> Vec<u8> {
    let mut bytes = Vec::new();
    let stats = archive_sevenz::pack(
        root,
        &mut Cursor::new(&mut bytes),
        &PackOptions {
            solid,
            ..PackOptions::default()
        },
        &ArchiveLimits::default(),
    )
    .unwrap();
    assert_eq!(stats.output_bytes, bytes.len() as u64);
    bytes
}
fn write_archive(path: &Path, bytes: &[u8]) {
    fs::write(path, bytes).unwrap();
}
fn malicious(name: &str, link: bool) -> Vec<u8> {
    let mut writer = ArchiveWriter::new(Cursor::new(Vec::new())).unwrap();
    let mut e = ArchiveEntry::new_file(name);
    if link {
        e.has_windows_attributes = true;
        e.windows_attributes = 0x400;
    }
    writer.push_archive_entry(e, Some(&b"x"[..])).unwrap();
    writer.finish().unwrap().into_inner()
}
fn named_archive(names: &[&str]) -> Vec<u8> {
    let mut writer = ArchiveWriter::new(Cursor::new(Vec::new())).unwrap();
    for name in names {
        writer
            .push_archive_entry(ArchiveEntry::new_file(name), Some(&b"x"[..]))
            .unwrap();
    }
    writer.finish().unwrap().into_inner()
}

#[test]
fn solid_and_non_solid_round_trip_include_unicode_and_empty_directories() {
    let parent = temp();
    let root = parent.join("tree");
    fs::create_dir_all(root.join("empty")).unwrap();
    fs::create_dir_all(root.join("子")).unwrap();
    fs::write(root.join("子/данные.bin"), [0, 255, 1, 2, 3, 0]).unwrap();
    fs::write(root.join("second.bin"), b"second solid stream").unwrap();
    fs::write(root.join("zero"), b"").unwrap();
    for solid in [true, false] {
        let bytes = output(&root, solid);
        let archive = parent.join(if solid { "solid.7z" } else { "plain.7z" });
        write_archive(&archive, &bytes);
        let info = archive_sevenz::info(&archive, &ReadLimits::default()).unwrap();
        assert_eq!(info["integrity_validated"], false);
        assert_eq!(info["solid"], solid);
        assert!(archive_sevenz::test(&archive, &ReadLimits::default()).is_ok());
        let dest = parent.join(if solid { "solid-out" } else { "plain-out" });
        archive_sevenz::unpack(&archive, &dest, &ReadLimits::default()).unwrap();
        assert_eq!(
            fs::read(dest.join("子/данные.bin")).unwrap(),
            [0, 255, 1, 2, 3, 0]
        );
        assert_eq!(
            fs::read(dest.join("second.bin")).unwrap(),
            b"second solid stream"
        );
        assert_eq!(fs::read(dest.join("zero")).unwrap(), b"");
        assert!(dest.join("empty").is_dir());
    }
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn trailing_empty_stream_metadata_round_trips_and_is_native_7z_compatible() {
    let parent = temp();
    let root = parent.join("many-empty-streams");
    fs::create_dir(&root).unwrap();
    // Sorted pathname order puts the empty file before the directories, making
    // the bitmap need to extend well past its last set bit.
    fs::write(root.join("000-empty"), b"").unwrap();
    for i in 0..96 {
        fs::create_dir(root.join(format!("directory-{i:03}"))).unwrap();
    }
    let known = b"known nonempty payload\0\xff";
    fs::write(root.join("zzz-payload.bin"), known).unwrap();

    let native_7z = ["7zz", "7z"]
        .iter()
        .find(|tool| Command::new(tool).arg("i").output().is_ok());
    for solid in [true, false] {
        let archive = parent.join(if solid { "solid.7z" } else { "plain.7z" });
        write_archive(&archive, &output(&root, solid));
        assert!(archive_sevenz::test(&archive, &ReadLimits::default()).is_ok());
        let restored = parent.join(if solid {
            "solid-restored"
        } else {
            "plain-restored"
        });
        archive_sevenz::unpack(&archive, &restored, &ReadLimits::default()).unwrap();
        assert_eq!(fs::read(restored.join("zzz-payload.bin")).unwrap(), known);
        assert_eq!(fs::read(restored.join("000-empty")).unwrap(), b"");
        for i in 0..96 {
            assert!(restored.join(format!("directory-{i:03}")).is_dir());
        }

        if let Some(tool) = native_7z {
            let native_restored = parent.join(if solid {
                "native-solid"
            } else {
                "native-plain"
            });
            let status = Command::new(tool)
                .arg("x")
                .arg("-y")
                .arg(format!("-o{}", native_restored.display()))
                .arg(&archive)
                .status()
                .unwrap();
            assert!(status.success(), "{tool} rejected {}", archive.display());
            assert_eq!(
                fs::read(native_restored.join("zzz-payload.bin")).unwrap(),
                known
            );
            assert_eq!(fs::read(native_restored.join("000-empty")).unwrap(), b"");
        }
    }
    if native_7z.is_none() {
        eprintln!(
            "native 7z interoperability assertion unavailable: neither 7zz nor 7z is installed"
        );
    }
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn empty_directory_root_and_empty_archive_are_valid() {
    let parent = temp();
    let root = parent.join("empty-root");
    fs::create_dir(&root).unwrap();
    let archive = parent.join("empty.7z");
    write_archive(&archive, &output(&root, true));
    assert_eq!(
        archive_sevenz::test(&archive, &ReadLimits::default())
            .unwrap()
            .output_bytes,
        0
    );
    let dest = parent.join("restored");
    archive_sevenz::unpack(&archive, &dest, &ReadLimits::default()).unwrap();
    assert!(dest.is_dir());
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn malformed_signature_header_crc_truncation_and_trailing_bytes_fail() {
    let parent = temp();
    let root = parent.join("in");
    fs::create_dir(&root).unwrap();
    fs::write(root.join("x"), b"data").unwrap();
    let good = output(&root, false);
    let mut cases = Vec::new();
    let mut bad = good.clone();
    bad[0] ^= 1;
    cases.push(bad);
    let mut bad = good.clone();
    bad[8] ^= 1;
    cases.push(bad);
    let mut bad = good.clone();
    bad[32] ^= 0x80;
    cases.push(bad);
    cases.push(good[..good.len() - 1].to_vec());
    let mut bad = good.clone();
    bad.push(0);
    cases.push(bad);
    for (i, bytes) in cases.iter().enumerate() {
        let p = parent.join(format!("bad-{i}.7z"));
        write_archive(&p, bytes);
        assert!(archive_sevenz::test(&p, &ReadLimits::default()).is_err());
    }
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn header_caps_and_output_entry_caps_reject_before_publication() {
    let parent = temp();
    let root = parent.join("in");
    fs::create_dir(&root).unwrap();
    fs::write(root.join("x"), b"payload").unwrap();
    let archive = parent.join("a.7z");
    write_archive(&archive, &output(&root, true));
    let limits = ReadLimits {
        max_header_bytes: 1,
        ..ReadLimits::default()
    };
    assert!(archive_sevenz::info(&archive, &limits).is_err());
    let limits = ReadLimits {
        archive: ArchiveLimits {
            max_total_bytes: 2,
            ..ArchiveLimits::default()
        },
        ..ReadLimits::default()
    };
    let dest = parent.join("must-not-exist");
    assert!(archive_sevenz::unpack(&archive, &dest, &limits).is_err());
    assert!(!dest.exists());

    for (i, limits) in [
        ReadLimits {
            archive: ArchiveLimits {
                max_entries: 0,
                ..ArchiveLimits::default()
            },
            ..ReadLimits::default()
        },
        ReadLimits {
            archive: ArchiveLimits {
                max_depth: 1,
                ..ArchiveLimits::default()
            },
            ..ReadLimits::default()
        },
    ]
    .iter()
    .enumerate()
    {
        let unsafe_archive = parent.join(format!("limit-{i}.7z"));
        write_archive(&unsafe_archive, &named_archive(&["nested/file"]));
        if i == 0 {
            assert!(
                archive_sevenz::info(&unsafe_archive, limits).is_err(),
                "the declared file count must fail during bounded header parsing"
            );
        }
        let out = parent.join(format!("limit-out-{i}"));
        assert!(archive_sevenz::unpack(&unsafe_archive, &out, limits).is_err());
        assert!(!out.exists());
    }
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn case_unicode_and_file_directory_aliases_are_rejected() {
    let parent = temp();
    for (i, names) in [
        vec!["Name", "name"],
        vec!["é", "e\u{301}"],
        vec!["parent", "parent/child"],
    ]
    .iter()
    .enumerate()
    {
        let archive = parent.join(format!("alias-{i}.7z"));
        write_archive(&archive, &named_archive(names));
        assert!(archive_sevenz::info(&archive, &ReadLimits::default()).is_err());
    }
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn encoded_header_declared_output_and_folder_dictionary_are_bounded() {
    let parent = temp();
    let root = parent.join("many-empty-directories");
    fs::create_dir(&root).unwrap();
    for i in 0..512 {
        fs::create_dir(root.join(format!("directory-{i:04}"))).unwrap();
    }
    let archive = parent.join("encoded-header.7z");
    write_archive(&archive, &output(&root, true));
    let bytes = fs::read(&archive).unwrap();
    let offset = u64::from_le_bytes(bytes[12..20].try_into().unwrap());
    let compressed_header = u64::from_le_bytes(bytes[20..28].try_into().unwrap());
    let start = (32 + offset) as usize;
    assert_eq!(
        bytes[start], 0x17,
        "fixture must exercise an encoded header"
    );
    assert!(compressed_header < 512 * 20);
    let limits = ReadLimits {
        max_header_bytes: compressed_header,
        ..ReadLimits::default()
    };
    assert!(
        archive_sevenz::info(&archive, &limits).is_err(),
        "decoded header must be capped before decoder construction"
    );

    let payload_root = parent.join("payload");
    fs::create_dir(&payload_root).unwrap();
    fs::write(payload_root.join("data"), vec![7u8; 4096]).unwrap();
    let payload_archive = parent.join("large-dictionary.7z");
    write_archive(&payload_archive, &output(&payload_root, false));
    let limits = ReadLimits {
        max_dictionary_bytes: 8 * 1024 * 1024,
        ..ReadLimits::default()
    };
    assert!(
        archive_sevenz::test(&payload_archive, &limits).is_err(),
        "data-folder dictionary must be capped before decode"
    );
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn traversal_and_link_metadata_are_rejected_without_writing_outside() {
    let parent = temp();
    for (i, bytes) in [malicious("../outside", false), malicious("link", true)]
        .iter()
        .enumerate()
    {
        let p = parent.join(format!("unsafe-{i}.7z"));
        write_archive(&p, bytes);
        let dest = parent.join(format!("out-{i}"));
        assert!(archive_sevenz::unpack(&p, &dest, &ReadLimits::default()).is_err());
        assert!(!dest.exists());
    }
    assert!(!parent.parent().unwrap().join("outside").exists());
    fs::remove_dir_all(parent).unwrap();
}

#[test]
fn signature_offset_and_next_header_crc_are_checked() {
    let parent = temp();
    let root = parent.join("in");
    fs::create_dir(&root).unwrap();
    let good = output(&root, false);
    let mut offset = good.clone();
    offset[12..20].copy_from_slice(&u64::MAX.to_le_bytes());
    let crc = crc32(&offset[12..32]);
    offset[8..12].copy_from_slice(&crc.to_le_bytes());
    let mut header_crc = good;
    let last = header_crc.len() - 1;
    header_crc[last] ^= 1;
    for (i, bytes) in [offset, header_crc].iter().enumerate() {
        let p = parent.join(format!("crc-{i}.7z"));
        write_archive(&p, bytes);
        assert!(archive_sevenz::info(&p, &ReadLimits::default()).is_err());
    }
    fs::remove_dir_all(parent).unwrap();
}
fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = !0u32;
    for &b in bytes {
        crc ^= b as u32;
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xEDB88320 & 0u32.wrapping_sub(crc & 1));
        }
    }
    !crc
}
