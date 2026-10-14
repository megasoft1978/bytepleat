use bytepleat::{codecs, DecodeOptions, EncodeOptions, Format};
use std::io::{self, Cursor};

#[test]
fn roundtrip_native_frames() {
    for format in [Format::Zstd, Format::Gzip, Format::Lz4] {
        let data = (0..1_100_000).map(|i| (i % 251) as u8).collect::<Vec<_>>();
        let opts = EncodeOptions {
            format,
            level: if format == Format::Lz4 { 0 } else { 3 },
            ..EncodeOptions::default()
        };
        let mut packed = Vec::new();
        codecs::compress(Cursor::new(&data), &mut packed, &opts).unwrap();
        let mut decoded = Vec::new();
        codecs::decompress(
            Cursor::new(&packed),
            &mut decoded,
            &DecodeOptions::default(),
        )
        .unwrap();
        assert_eq!(data, decoded);
    }
}
#[test]
fn producer_and_consumer_can_be_short() {
    let mut z = Vec::new();
    let o = EncodeOptions::default();
    codecs::encode_with(&mut z, &o, |w| {
        w.write_all(b"sample")?;
        Ok(())
    })
    .unwrap();
    codecs::decode_with(Cursor::new(z), &DecodeOptions::default(), |r| {
        let mut b = [0; 1];
        r.read_exact(&mut b)?;
        Ok(())
    })
    .unwrap();
}
#[test]
fn rejects_unknown_and_trailing_data() {
    assert!(codecs::detect_format(b"plain").is_err());
    let mut z = Vec::new();
    codecs::compress(Cursor::new(b"x"), &mut z, &EncodeOptions::default()).unwrap();
    z.extend_from_slice(b"garbage");
    assert!(
        codecs::decode_with(Cursor::new(z), &DecodeOptions::default(), |r| io::copy(
            r,
            &mut io::sink()
        )
        .map(|_| ()))
        .is_err()
    );
}

#[test]
fn output_limit_and_gzip_members() {
    let mut packed = Vec::new();
    let opts = EncodeOptions {
        format: Format::Gzip,
        ..EncodeOptions::default()
    };
    codecs::compress(Cursor::new(b"first"), &mut packed, &opts).unwrap();
    codecs::compress(Cursor::new(b"second"), &mut packed, &opts).unwrap();
    let mut decoded = Vec::new();
    codecs::decompress(
        Cursor::new(&packed),
        &mut decoded,
        &DecodeOptions::default(),
    )
    .unwrap();
    assert_eq!(decoded, b"firstsecond");
    assert!(codecs::decode_with(
        Cursor::new(packed),
        &DecodeOptions {
            max_output: 3,
            ..DecodeOptions::default()
        },
        |r| io::copy(r, &mut io::sink()).map(|_| ())
    )
    .is_err());
}

#[test]
fn native_checksums_are_verified() {
    for format in [Format::Zstd, Format::Gzip, Format::Lz4] {
        let mut packed = Vec::new();
        let opts = EncodeOptions {
            format,
            level: if format == Format::Lz4 { 0 } else { 3 },
            ..EncodeOptions::default()
        };
        codecs::compress(Cursor::new(b"checksum payload"), &mut packed, &opts).unwrap();
        let last = packed.len() - 1;
        packed[last] ^= 1;
        assert!(
            codecs::decode_with(Cursor::new(packed), &DecodeOptions::default(), |r| {
                io::copy(r, &mut io::sink()).map(|_| ())
            })
            .is_err(),
            "{format:?}"
        );
    }
}
