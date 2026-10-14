use crate::{invalid, numeric, DecodeOptions, EncodeOptions, Format, Stats};
use flate2::{read::MultiGzDecoder, write::GzEncoder, Compression};
use lz4_flex::frame::FrameDecoder;
#[cfg(feature = "lz4-flex")]
use lz4_flex::frame::{FrameEncoder, FrameInfo};
use std::cell::Cell;
use std::io::{self, Cursor, Read, Write};
use std::rc::Rc;

const BUFFER: usize = 64 * 1024;

#[cfg(any(
    all(feature = "gzip-zlib-rs", feature = "gzip-miniz"),
    not(any(feature = "gzip-zlib-rs", feature = "gzip-miniz"))
))]
compile_error!("enable exactly one gzip backend: gzip-zlib-rs or gzip-miniz");

#[cfg(any(
    all(feature = "lz4-native", feature = "lz4-flex"),
    not(any(feature = "lz4-native", feature = "lz4-flex"))
))]
compile_error!("enable exactly one LZ4 encoder: lz4-native or lz4-flex");

struct CountRead<R>(R, Rc<Cell<u64>>);
impl<R: Read> Read for CountRead<R> {
    fn read(&mut self, b: &mut [u8]) -> io::Result<usize> {
        if b.is_empty() {
            return Ok(0);
        }
        let n = loop {
            match self.0.read(b) {
                Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                r => break r?,
            }
        };
        self.1.set(self.1.get() + n as u64);
        Ok(n)
    }
}
struct CountWrite<W>(W, u64);
impl<W: Write> Write for CountWrite<W> {
    fn write(&mut self, b: &[u8]) -> io::Result<usize> {
        let n = self.0.write(b)?;
        self.1 += n as u64;
        Ok(n)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.0.flush()
    }
}

fn validate_encode(o: &EncodeOptions) -> io::Result<()> {
    if o.format == Format::Pco {
        if o.numeric_type.is_none() {
            return Err(invalid("pco requires an explicit numeric type"));
        }
        return Ok(());
    }
    if o.numeric_type.is_some() {
        return Err(invalid("numeric type is only valid for pco"));
    }
    match o.format {
        Format::Zstd if !(1..=22).contains(&o.level) || !(1..=256).contains(&o.threads) => {
            Err(invalid("zstd level must be 1..22 and threads 1..256"))
        }
        Format::Gzip if !(0..=9).contains(&o.level) => Err(invalid("gzip level must be 0..9")),
        Format::Gzip | Format::Lz4 if o.threads != 1 => {
            Err(invalid("gzip and lz4 support one thread only"))
        }
        Format::Lz4 if o.level != 0 => Err(invalid("lz4 supports only its standard level (0)")),
        _ => Ok(()),
    }
}

pub fn encode_with<W: Write>(
    output: W,
    opts: &EncodeOptions,
    produce: impl FnOnce(&mut dyn Write) -> io::Result<()>,
) -> io::Result<Stats> {
    validate_encode(opts)?;
    let mut out = CountWrite(output, 0);
    let mut input_count = 0u64;
    if opts.format == Format::Pco {
        return Err(invalid("pco encode_with is unsupported; use compress"));
    }
    match opts.format {
        Format::Zstd => {
            let mut e = zstd::stream::write::Encoder::new(&mut out, opts.level)?;
            e.include_checksum(true)?;
            if opts.threads > 1 {
                e.multithread(opts.threads)?;
            }
            {
                let mut w = InputCounter {
                    inner: &mut e,
                    count: &mut input_count,
                };
                produce(&mut w)?;
            }
            e.finish()?;
        }
        Format::Gzip => {
            let mut e = GzEncoder::new(&mut out, Compression::new(opts.level as u32));
            {
                let mut w = InputCounter {
                    inner: &mut e,
                    count: &mut input_count,
                };
                produce(&mut w)?;
            }
            e.finish()?;
        }
        Format::Lz4 => {
            #[cfg(feature = "lz4-native")]
            {
                use lz4::liblz4::{BlockChecksum, BlockMode, BlockSize, ContentChecksum};
                let mut builder = lz4::EncoderBuilder::new();
                let mut e = builder
                    .block_size(BlockSize::Max64KB)
                    .block_mode(BlockMode::Independent)
                    .block_checksum(BlockChecksum::BlockChecksumEnabled)
                    .checksum(ContentChecksum::ChecksumEnabled)
                    .level(0)
                    .build(&mut out)?;
                {
                    let mut w = InputCounter {
                        inner: &mut e,
                        count: &mut input_count,
                    };
                    produce(&mut w)?;
                }
                let (_, result) = e.finish();
                result?;
            }
            #[cfg(feature = "lz4-flex")]
            {
                let info = FrameInfo::new()
                    .content_checksum(true)
                    .block_checksums(true);
                let sink = FlexErrorWriter(&mut out);
                let mut e = FrameEncoder::with_frame_info(info, sink);
                {
                    let mut w = InputCounter {
                        inner: &mut e,
                        count: &mut input_count,
                    };
                    produce(&mut w)?;
                }
                e.finish()?;
            }
        }
        Format::Pco => unreachable!(),
    }
    Ok(Stats {
        input_bytes: input_count,
        output_bytes: out.1,
    })
}
struct InputCounter<'a> {
    inner: &'a mut dyn Write,
    count: &'a mut u64,
}

// lz4_flex 0.11's Error::from(io::Error) assumes any attached error source is its
// own Error type. Preserve output errors inside that type to avoid its downcast panic.
#[cfg(feature = "lz4-flex")]
struct FlexErrorWriter<W>(W);
#[cfg(feature = "lz4-flex")]
impl<W: Write> Write for FlexErrorWriter<W> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0.write(bytes).map_err(wrap_flex_error)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.0.flush().map_err(wrap_flex_error)
    }
}
#[cfg(feature = "lz4-flex")]
fn wrap_flex_error(error: io::Error) -> io::Error {
    let kind = error.kind();
    io::Error::new(kind, lz4_flex::frame::Error::IoError(error))
}
impl Write for InputCounter<'_> {
    fn write(&mut self, b: &[u8]) -> io::Result<usize> {
        let n = self.inner.write(b)?;
        *self.count += n as u64;
        Ok(n)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.inner.flush()
    }
}

pub fn compress<R: Read, W: Write>(
    mut input: R,
    output: W,
    opts: &EncodeOptions,
) -> io::Result<Stats> {
    if opts.format == Format::Pco {
        let count = Rc::new(Cell::new(0));
        let mut source = CountRead(input, count.clone());
        let mut target = CountWrite(output, 0);
        numeric::compress(&mut source, &mut target, opts)?;
        return Ok(Stats {
            input_bytes: count.get(),
            output_bytes: target.1,
        });
    }
    let mut count = 0u64;
    let mut result = encode_with(output, opts, |w| {
        let mut buf = [0u8; BUFFER];
        loop {
            let n = input.read(&mut buf)?;
            if n == 0 {
                break;
            }
            w.write_all(&buf[..n])?;
            count += n as u64;
        }
        Ok(())
    })?;
    result.input_bytes = count;
    Ok(result)
}

pub fn detect_format(p: &[u8]) -> io::Result<Format> {
    if p.starts_with(&[0x28, 0xb5, 0x2f, 0xfd])
        || (p.len() >= 4
            && u32::from_le_bytes(p[..4].try_into().unwrap()) & 0xfffffff0 == 0x184d2a50)
    {
        return Ok(Format::Zstd);
    }
    if p.starts_with(&[0x1f, 0x8b]) {
        return Ok(Format::Gzip);
    }
    if p.starts_with(&[0x04, 0x22, 0x4d, 0x18]) {
        return Ok(Format::Lz4);
    }
    if p.starts_with(b"pco!") {
        return Ok(Format::Pco);
    }
    Err(invalid("unrecognized compression format"))
}

pub fn decompress<R: Read, W: Write>(
    mut input: R,
    output: W,
    opts: &DecodeOptions,
) -> io::Result<Stats> {
    let mut prefix = [0u8; 8];
    let mut plen = 0;
    while plen < prefix.len() {
        let n = input.read(&mut prefix[plen..])?;
        if n == 0 {
            break;
        }
        plen += n;
    }
    let format = detect_format(&prefix[..plen])?;
    if format != Format::Pco && opts.numeric_type.is_some() {
        return Err(invalid("numeric type is only valid for pco"));
    }
    if format == Format::Pco {
        let consumed = Rc::new(Cell::new(plen as u64));
        let rest = CountRead(input, consumed.clone());
        let mut source = Cursor::new(prefix[..plen].to_vec()).chain(rest);
        let mut target = CountWrite(output, 0);
        numeric::decompress(&mut source, &mut target, opts)?;
        return Ok(Stats {
            input_bytes: consumed.get(),
            output_bytes: target.1,
        });
    }
    let input = Cursor::new(prefix[..plen].to_vec()).chain(input);
    let mut written = 0u64;
    let mut out = CountWrite(output, 0);
    let base = decode_with(input, opts, |r| {
        let mut buf = [0u8; BUFFER];
        loop {
            let n = r.read(&mut buf)?;
            if n == 0 {
                break;
            }
            out.write_all(&buf[..n])?;
            written += n as u64;
        }
        Ok(())
    })?;
    Ok(Stats {
        input_bytes: base.input_bytes,
        output_bytes: written,
    })
}

pub fn decode_with<R: Read>(
    input: R,
    opts: &DecodeOptions,
    consume: impl FnOnce(&mut dyn Read) -> io::Result<()>,
) -> io::Result<Stats> {
    let consumed = Rc::new(Cell::new(0));
    let mut counted = CountRead(input, consumed.clone());
    let mut prefix = [0; 8];
    let mut plen = 0;
    while plen < 8 {
        let n = counted.read(&mut prefix[plen..])?;
        if n == 0 {
            break;
        }
        plen += n;
    }
    let fmt = detect_format(&prefix[..plen])?;
    if fmt != Format::Pco && opts.numeric_type.is_some() {
        return Err(invalid("numeric type is only valid for pco"));
    }
    let chained = Cursor::new(prefix[..plen].to_vec()).chain(counted);
    if fmt == Format::Pco {
        return Err(invalid("pco decode_with is unsupported; use decompress"));
    }
    let mut decoder: Box<dyn Read> = match fmt {
        Format::Zstd => {
            let mut d = zstd::stream::read::Decoder::new(chained)?;
            d.window_log_max(opts.max_window_log)?;
            Box::new(d)
        }
        Format::Gzip => Box::new(MultiGzDecoder::new(chained)),
        Format::Lz4 => Box::new(StrictLz4 {
            decoder: FrameDecoder::new(chained),
            ended: false,
        }),
        Format::Pco => unreachable!(),
    };
    let mut capped = CapRead {
        inner: &mut decoder,
        read: 0,
        limit: opts.max_output,
    };
    let result = consume(&mut capped);
    if let Err(e) = result {
        return Err(e);
    }
    let drain = io::copy(&mut capped, &mut io::sink());
    let output = capped.read;
    result?;
    drain?;
    // Decoder completion forces checksum and truncation validation. The LZ4 crate exposes only
    // one frame per decoder; reject any unread suffix rather than silently accepting it.
    Ok(Stats {
        input_bytes: consumed.get(),
        output_bytes: output,
    })
}
struct CapRead<'a, R> {
    inner: &'a mut R,
    read: u64,
    limit: u64,
}

struct StrictLz4<R: Read> {
    decoder: FrameDecoder<R>,
    ended: bool,
}
impl<R: Read> Read for StrictLz4<R> {
    fn read(&mut self, out: &mut [u8]) -> io::Result<usize> {
        if out.is_empty() {
            return Ok(0);
        }
        if self.ended {
            return Ok(0);
        }
        let n = self.decoder.read(out)?;
        if n == 0 {
            let mut tail = [0u8; 1];
            if self.decoder.get_mut().read(&mut tail)? != 0 {
                return Err(invalid(
                    "trailing data or concatenated LZ4 frames are unsupported",
                ));
            }
            self.ended = true;
        }
        Ok(n)
    }
}
impl<R: Read> Read for CapRead<'_, R> {
    fn read(&mut self, b: &mut [u8]) -> io::Result<usize> {
        if b.is_empty() {
            return Ok(0);
        }
        if self.read >= self.limit {
            let mut probe = [0];
            return match self.inner.read(&mut probe)? {
                0 => Ok(0),
                _ => Err(invalid("decompressed output exceeds configured limit")),
            };
        }
        let max = (self.limit - self.read).min(b.len() as u64) as usize;
        let n = self.inner.read(&mut b[..max])?;
        self.read += n as u64;
        Ok(n)
    }
}
