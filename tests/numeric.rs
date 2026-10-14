use std::io::Cursor;

use arqlet::{numeric, DecodeOptions, EncodeOptions, Format, NumericType};

fn roundtrip(t: NumericType, bytes: &[u8]) {
    let enc = EncodeOptions {
        format: Format::Pco,
        numeric_type: Some(t),
        ..EncodeOptions::default()
    };
    let dec = DecodeOptions {
        numeric_type: Some(t),
        ..DecodeOptions::default()
    };
    let mut packed = Vec::new();
    numeric::compress(&mut Cursor::new(bytes), &mut packed, &enc).unwrap();
    let mut restored = Vec::new();
    numeric::decompress(&mut Cursor::new(packed), &mut restored, &dec).unwrap();
    assert_eq!(restored, bytes);
}

#[test]
fn integer_types_and_multichunk_extrema() {
    let mut b = Vec::new();
    for i in 0..700_000i32 {
        b.extend_from_slice(&if i % 2 == 0 { i32::MIN } else { i32::MAX }.to_le_bytes());
    }
    roundtrip(NumericType::I32, &b);
    for (t, b) in [
        (
            NumericType::U32,
            [0, u32::MAX, 1, 0x8000_0000]
                .into_iter()
                .flat_map(u32::to_le_bytes)
                .collect::<Vec<_>>(),
        ),
        (
            NumericType::I64,
            [i64::MIN, -1, 0, i64::MAX]
                .into_iter()
                .flat_map(i64::to_le_bytes)
                .collect::<Vec<_>>(),
        ),
        (
            NumericType::U64,
            [0, u64::MAX, 1, 0x8000_0000_0000_0000]
                .into_iter()
                .flat_map(u64::to_le_bytes)
                .collect::<Vec<_>>(),
        ),
    ] {
        roundtrip(t, &b);
    }
}

#[test]
fn float_edge_bit_patterns_are_exact() {
    let f32s = [
        0,
        0x8000_0000,
        0x7f80_0000,
        0xff80_0000,
        1,
        0x007f_ffff,
        0x7fc0_0001,
        0x7fa1_2345,
        0xffc5_4321,
    ];
    roundtrip(
        NumericType::F32,
        &f32s
            .into_iter()
            .flat_map(u32::to_le_bytes)
            .collect::<Vec<_>>(),
    );
    let f64s = [
        0,
        0x8000_0000_0000_0000,
        0x7ff0_0000_0000_0000,
        0xfff0_0000_0000_0000,
        1,
        0x000f_ffff_ffff_ffff,
        0x7ff8_0000_0000_0001,
        0x7ff1_2345_6789_abcd,
        0xfff8_9876_5432_1000,
    ];
    roundtrip(
        NumericType::F64,
        &f64s
            .into_iter()
            .flat_map(u64::to_le_bytes)
            .collect::<Vec<_>>(),
    );
}

#[test]
fn rejects_unaligned_input_missing_type_wrong_type_and_limits() {
    let enc = EncodeOptions {
        format: Format::Pco,
        numeric_type: Some(NumericType::I32),
        ..EncodeOptions::default()
    };
    assert!(numeric::compress(&mut Cursor::new([1, 2, 3]), &mut Vec::new(), &enc).is_err());
    assert!(numeric::compress(
        &mut Cursor::new([0u8; 4]),
        &mut Vec::new(),
        &EncodeOptions {
            format: Format::Pco,
            ..EncodeOptions::default()
        }
    )
    .is_err());
    let mut pco = Vec::new();
    numeric::compress(&mut Cursor::new(1i32.to_le_bytes()), &mut pco, &enc).unwrap();
    assert!(numeric::decompress(
        &mut Cursor::new(&pco),
        &mut Vec::new(),
        &DecodeOptions {
            numeric_type: None,
            ..DecodeOptions::default()
        }
    )
    .is_err());
    assert!(numeric::decompress(
        &mut Cursor::new(&pco),
        &mut Vec::new(),
        &DecodeOptions {
            numeric_type: Some(NumericType::U32),
            ..DecodeOptions::default()
        }
    )
    .is_err());
    assert!(numeric::decompress(
        &mut Cursor::new(&pco),
        &mut Vec::new(),
        &DecodeOptions {
            max_output: 3,
            numeric_type: Some(NumericType::I32),
            ..DecodeOptions::default()
        }
    )
    .is_err());
    pco.push(0x42);
    assert!(numeric::decompress(
        &mut Cursor::new(&pco),
        &mut Vec::new(),
        &DecodeOptions {
            numeric_type: Some(NumericType::I32),
            ..DecodeOptions::default()
        }
    )
    .is_err());
}

#[test]
fn empty_and_truncated_streams() {
    let enc = EncodeOptions {
        format: Format::Pco,
        numeric_type: Some(NumericType::I64),
        ..EncodeOptions::default()
    };
    let dec = DecodeOptions {
        numeric_type: Some(NumericType::I64),
        ..DecodeOptions::default()
    };
    let mut pco = Vec::new();
    numeric::compress(&mut Cursor::new([]), &mut pco, &enc).unwrap();
    assert!(numeric::decompress(&mut Cursor::new(&pco), &mut Vec::new(), &dec).is_ok());
    pco.pop();
    assert!(numeric::decompress(&mut Cursor::new(&pco), &mut Vec::new(), &dec).is_err());
}
