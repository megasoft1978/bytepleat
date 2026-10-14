use arqlet::{codecs, DecodeOptions, EncodeOptions, Format};
use std::io::{self, Cursor, Read, Write};

fn options(format: Format) -> EncodeOptions {
    EncodeOptions {
        format,
        level: if format == Format::Lz4 { 0 } else { 3 },
        ..EncodeOptions::default()
    }
}

fn decode(bytes: &[u8]) -> io::Result<Vec<u8>> {
    let mut out = Vec::new();
    codecs::decode_with(Cursor::new(bytes), &DecodeOptions::default(), |r| {
        r.read_to_end(&mut out)?;
        Ok(())
    })?;
    Ok(out)
}

#[test]
fn selected_encoders_interoperate_with_existing_decoders() {
    let input = (0..220_000).map(|i| (i % 239) as u8).collect::<Vec<_>>();
    for format in [Format::Gzip, Format::Lz4] {
        let mut frame = Vec::new();
        let stats = codecs::compress(Cursor::new(&input), &mut frame, &options(format)).unwrap();
        assert_eq!(stats.input_bytes, input.len() as u64);
        assert_eq!(stats.output_bytes, frame.len() as u64);
        assert_eq!(decode(&frame).unwrap(), input, "{format:?}");
    }
}

#[test]
fn gzip_accepts_members_but_rejects_trailing_bytes() {
    let mut frame = Vec::new();
    for part in [b"first".as_slice(), b"second".as_slice()] {
        let mut encoder = flate2::write::GzEncoder::new(&mut frame, flate2::Compression::default());
        encoder.write_all(part).unwrap();
        encoder.finish().unwrap();
    }
    assert_eq!(decode(&frame).unwrap(), b"firstsecond");
    frame.extend_from_slice(b"tail");
    assert!(decode(&frame).is_err());
}

#[test]
fn candidate_frames_reject_truncation_and_checksum_corruption() {
    for format in [Format::Gzip, Format::Lz4] {
        let mut frame = Vec::new();
        codecs::compress(Cursor::new(vec![17; 100_000]), &mut frame, &options(format)).unwrap();

        let mut truncated = frame.clone();
        truncated.pop();
        assert!(decode(&truncated).is_err(), "truncated {format:?}");

        let mut corrupt = frame;
        let pos = corrupt.len() / 2;
        corrupt[pos] ^= 0x40;
        assert!(decode(&corrupt).is_err(), "corrupt {format:?}");
    }
}

struct ShortWriter(Vec<u8>);
impl Write for ShortWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        let n = bytes.len().min(3);
        self.0.extend_from_slice(&bytes[..n]);
        Ok(n)
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[test]
fn short_output_writes_are_completed() {
    let input = b"short writes must not lose compressed bytes";
    let mut writer = ShortWriter(Vec::new());
    let stats = codecs::compress(Cursor::new(input), &mut writer, &options(Format::Lz4)).unwrap();
    assert_eq!(stats.input_bytes, input.len() as u64);
    assert_eq!(stats.output_bytes, writer.0.len() as u64);
    assert_eq!(decode(&writer.0).unwrap(), input);
}

struct ShortInterruptedReader<R> {
    inner: R,
    interrupt_next: bool,
}
impl<R: Read> Read for ShortInterruptedReader<R> {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        if self.interrupt_next {
            self.interrupt_next = false;
            return Err(io::Error::from(io::ErrorKind::Interrupted));
        }
        let max = bytes.len().min(2);
        self.inner.read(&mut bytes[..max])
    }
}

#[test]
fn counted_decode_retries_interrupted_short_reads_and_reports_counts() {
    let payload = b"short interrupted input reads";
    let mut frame = Vec::new();
    let encoded =
        codecs::compress(Cursor::new(payload), &mut frame, &options(Format::Gzip)).unwrap();
    let reader = ShortInterruptedReader {
        inner: Cursor::new(frame),
        interrupt_next: true,
    };
    let mut decoded = Vec::new();
    let stats = codecs::decode_with(reader, &DecodeOptions::default(), |r| {
        r.read_to_end(&mut decoded)?;
        Ok(())
    })
    .unwrap();
    assert_eq!(decoded, payload);
    assert_eq!(encoded.output_bytes, stats.input_bytes);
    assert_eq!(stats.output_bytes, payload.len() as u64);
}

struct FailingWriter {
    remaining: usize,
}
impl Write for FailingWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if self.remaining == 0 {
            return Err(io::Error::other("injected output failure"));
        }
        let n = bytes.len().min(self.remaining);
        self.remaining -= n;
        Ok(n)
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[test]
fn producer_and_encoder_finish_failures_are_returned() {
    let err = codecs::encode_with(Vec::new(), &options(Format::Gzip), |_w| {
        Err(io::Error::other("injected producer failure"))
    })
    .unwrap_err();
    assert!(err.to_string().contains("producer failure"));

    // Permit the header and body writes, then fail when the encoder writes its trailer.
    let err = codecs::encode_with(
        FailingWriter { remaining: 11 },
        &options(Format::Lz4),
        |w| w.write_all(b"payload"),
    )
    .unwrap_err();
    assert!(err.to_string().contains("output failure"));
}
