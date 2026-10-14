//! Native standalone Pco streams for explicitly typed little-endian words.
//!
//! Decoding streams through Pco's buffered-reader interface and bounds both
//! compressed input and decoded chunks.
use better_io::{BetterBufRead, BetterBufReader};
use std::io::{self, Read, Write};
use std::{cell::Cell, rc::Rc};

use pco::{
    data_types::{Number, NumberType},
    standalone::{DecompressorItem, FileCompressor, FileDecompressor},
    ChunkConfig,
};

use crate::{invalid, DecodeOptions, EncodeOptions, NumericType, Stats};

const IO_CHUNK: usize = 1024 * 1024;
const MAX_COMPRESSED_INPUT: u64 = 1024 * 1024 * 1024;

fn numeric_type(t: Option<NumericType>) -> io::Result<NumericType> {
    t.ok_or_else(|| invalid("Pco requires an explicit numeric type"))
}
fn pco_type(t: NumericType) -> NumberType {
    match t {
        NumericType::I32 => NumberType::I32,
        NumericType::U32 => NumberType::U32,
        NumericType::I64 => NumberType::I64,
        NumericType::U64 => NumberType::U64,
        NumericType::F32 => NumberType::F32,
        NumericType::F64 => NumberType::F64,
    }
}
fn pco_error(e: impl std::fmt::Display) -> io::Error {
    invalid(format!("invalid Pco stream: {e}"))
}
fn check_encode(opts: &EncodeOptions) -> io::Result<NumericType> {
    let t = numeric_type(opts.numeric_type)?;
    if opts.format != crate::Format::Pco {
        return Err(invalid("numeric codec requires format pco"));
    }
    if !(0..=12).contains(&opts.level) {
        return Err(invalid("Pco level must be between 0 and 12"));
    }
    if opts.threads > 1 {
        return Err(invalid("Pco does not support more than one thread"));
    }
    Ok(t)
}

/// Encode a little-endian typed numeric stream as a standalone `.pco` file.
pub fn compress(
    input: &mut dyn Read,
    output: &mut dyn Write,
    opts: &EncodeOptions,
) -> io::Result<Stats> {
    let t = check_encode(opts)?;
    let fc = FileCompressor::default().with_uniform_type(Some(pco_type(t)));
    let mut counted = CountWriter {
        inner: output,
        count: 0,
    };
    fc.write_header(&mut counted).map_err(pco_error)?;
    let width = t.width();
    let mut bytes = vec![0u8; IO_CHUNK];
    let mut stats = Stats::default();
    let mut config = ChunkConfig::default();
    config.compression_level = opts.level as usize;
    loop {
        let mut used = 0usize;
        let eof = loop {
            if used == bytes.len() {
                break false;
            }
            match input.read(&mut bytes[used..]) {
                Ok(0) => break true,
                Ok(n) => used += n,
                Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                Err(e) => return Err(e),
            }
        };
        if eof && !used.is_multiple_of(width) {
            return Err(invalid("input ends with a partial numeric word"));
        }
        if used > 0 {
            encode_chunk(&fc, &config, t, &bytes[..used], &mut counted)?;
            stats.input_bytes += used as u64;
        }
        if eof {
            break;
        }
    }
    fc.write_footer(&mut counted).map_err(pco_error)?;
    stats.output_bytes = counted.count;
    Ok(stats)
}

fn encode_chunk(
    fc: &FileCompressor,
    config: &ChunkConfig,
    t: NumericType,
    bytes: &[u8],
    out: &mut dyn Write,
) -> io::Result<()> {
    macro_rules! run {
        ($ty:ty, $conv:expr) => {{
            let values: Vec<$ty> = bytes
                .chunks_exact(std::mem::size_of::<$ty>())
                .map(|b| $conv(b))
                .collect();
            let mut cc = fc.chunk_compressor(&values, config).map_err(pco_error)?;
            cc.write(out).map_err(pco_error)?;
        }};
    }
    match t {
        NumericType::I32 => run!(i32, |b: &[u8]| i32::from_le_bytes(b.try_into().unwrap())),
        NumericType::U32 => run!(u32, |b: &[u8]| u32::from_le_bytes(b.try_into().unwrap())),
        NumericType::I64 => run!(i64, |b: &[u8]| i64::from_le_bytes(b.try_into().unwrap())),
        NumericType::U64 => run!(u64, |b: &[u8]| u64::from_le_bytes(b.try_into().unwrap())),
        NumericType::F32 => run!(f32, |b: &[u8]| f32::from_bits(u32::from_le_bytes(
            b.try_into().unwrap()
        ))),
        NumericType::F64 => run!(f64, |b: &[u8]| f64::from_bits(u64::from_le_bytes(
            b.try_into().unwrap()
        ))),
    }
    Ok(())
}

/// Decode a standalone `.pco` stream into little-endian words of the required type.
pub fn decompress(
    input: &mut dyn Read,
    output: &mut dyn Write,
    opts: &DecodeOptions,
) -> io::Result<Stats> {
    let t = numeric_type(opts.numeric_type)?;
    let count = Rc::new(Cell::new(0));
    let counted = InputCounter {
        inner: input,
        count: count.clone(),
    };
    let capped = CappedRead {
        inner: counted,
        read: 0,
    };
    let src = BetterBufReader::from_read_simple(capped);
    let (fd, src) = FileDecompressor::new(src).map_err(pco_error)?;
    if fd.uniform_type().is_some_and(|got| got != pco_type(t)) {
        return Err(invalid("Pco numeric type does not match requested type"));
    }
    let mut counted = CountWriter {
        inner: output,
        count: 0,
    };
    macro_rules! run {
        ($ty:ty) => {{
            decode_t::<$ty, _>(&fd, src, &mut counted, opts.max_output)?;
        }};
    }
    match t {
        NumericType::I32 => run!(i32),
        NumericType::U32 => run!(u32),
        NumericType::I64 => run!(i64),
        NumericType::U64 => run!(u64),
        NumericType::F32 => run!(f32),
        NumericType::F64 => run!(f64),
    }
    Ok(Stats {
        input_bytes: count.get(),
        output_bytes: counted.count,
    })
}

struct InputCounter<'a> {
    inner: &'a mut dyn Read,
    count: Rc<Cell<u64>>,
}
impl Read for InputCounter<'_> {
    fn read(&mut self, b: &mut [u8]) -> io::Result<usize> {
        if b.is_empty() {
            return Ok(0);
        }
        loop {
            match self.inner.read(b) {
                Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                result => {
                    let n = result?;
                    self.count.set(self.count.get() + n as u64);
                    return Ok(n);
                }
            }
        }
    }
}
struct CappedRead<R> {
    inner: R,
    read: u64,
}
impl<R: Read> Read for CappedRead<R> {
    fn read(&mut self, b: &mut [u8]) -> io::Result<usize> {
        if b.is_empty() {
            return Ok(0);
        }
        let room = MAX_COMPRESSED_INPUT.saturating_sub(self.read);
        let cap = (room + 1).min(b.len() as u64) as usize;
        let n = self.inner.read(&mut b[..cap])?;
        self.read += n as u64;
        if self.read > MAX_COMPRESSED_INPUT {
            return Err(invalid("compressed Pco input exceeds 1 GiB safety limit"));
        }
        Ok(n)
    }
}

struct CountWriter<'a> {
    inner: &'a mut dyn Write,
    count: u64,
}
impl Write for CountWriter<'_> {
    fn write(&mut self, b: &[u8]) -> io::Result<usize> {
        let n = self.inner.write(b)?;
        self.count += n as u64;
        Ok(n)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.inner.flush()
    }
}
trait LeBytes {
    fn write_le(self, out: &mut dyn Write) -> io::Result<()>;
}
macro_rules! le_bytes { ($($t:ty),*) => {$ (impl LeBytes for $t { fn write_le(self, out:&mut dyn Write)->io::Result<()> { out.write_all(&self.to_le_bytes()) } })*} }
le_bytes!(i32, u32, i64, u64);
impl LeBytes for f32 {
    fn write_le(self, out: &mut dyn Write) -> io::Result<()> {
        out.write_all(&self.to_bits().to_le_bytes())
    }
}
impl LeBytes for f64 {
    fn write_le(self, out: &mut dyn Write) -> io::Result<()> {
        out.write_all(&self.to_bits().to_le_bytes())
    }
}

fn decode_t<T: Number + LeBytes, R: BetterBufRead>(
    fd: &FileDecompressor,
    mut src: R,
    output: &mut CountWriter<'_>,
    max_output: u64,
) -> io::Result<()> {
    loop {
        match fd.chunk_decompressor::<T, _>(src).map_err(pco_error)? {
            DecompressorItem::EndOfData(mut rest) => {
                if !rest.fill_or_eof(1).map_err(pco_error)?.is_empty() {
                    return Err(invalid("trailing bytes after Pco end marker"));
                }
                return Ok(());
            }
            DecompressorItem::Chunk(mut chunk) => {
                let n = chunk.n();
                let bytes = (n as u64)
                    .checked_mul(std::mem::size_of::<T>() as u64)
                    .ok_or_else(|| invalid("Pco chunk byte count overflow"))?;
                if bytes > IO_CHUNK as u64 {
                    return Err(invalid("Pco chunk exceeds 1 MiB"));
                }
                if output
                    .count
                    .checked_add(bytes)
                    .filter(|&v| v <= max_output)
                    .is_none()
                {
                    return Err(invalid("decoded output exceeds configured maximum"));
                }
                let mut values = Vec::with_capacity(n);
                values.resize_with(n, T::default);
                let progress = chunk.read(&mut values).map_err(pco_error)?;
                if progress.n_processed != n || !progress.finished {
                    return Err(invalid("incomplete Pco chunk"));
                }
                let mut serialized = Vec::with_capacity(bytes as usize);
                for value in values {
                    value.write_le(&mut serialized)?;
                }
                output.write_all(&serialized)?;
                src = chunk.into_src();
            }
        }
    }
}
