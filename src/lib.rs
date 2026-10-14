//! A byte-preserving facade over established compression formats.
use serde::Serialize;
use std::{io, str::FromStr};
pub mod archive;
pub mod archive_safety;
pub mod archive_sevenz;
pub mod archive_zip;
pub mod codecs;
pub mod file_io;
pub mod numeric;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Format {
    Zstd,
    Gzip,
    Lz4,
    Pco,
}
impl FromStr for Format {
    type Err = String;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "zstd" => Ok(Self::Zstd),
            "gzip" => Ok(Self::Gzip),
            "lz4" => Ok(Self::Lz4),
            "pco" => Ok(Self::Pco),
            _ => Err(format!("unknown format: {s}")),
        }
    }
}
impl Format {
    pub fn extension(self) -> &'static str {
        match self {
            Self::Zstd => "zst",
            Self::Gzip => "gz",
            Self::Lz4 => "lz4",
            Self::Pco => "pco",
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum NumericType {
    I32,
    U32,
    I64,
    U64,
    F32,
    F64,
}
impl FromStr for NumericType {
    type Err = String;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "i32" => Ok(Self::I32),
            "u32" => Ok(Self::U32),
            "i64" => Ok(Self::I64),
            "u64" => Ok(Self::U64),
            "f32" => Ok(Self::F32),
            "f64" => Ok(Self::F64),
            _ => Err(format!("unknown numeric type: {s}")),
        }
    }
}
impl NumericType {
    pub fn width(self) -> usize {
        match self {
            Self::I32 | Self::U32 | Self::F32 => 4,
            _ => 8,
        }
    }
}
#[derive(Debug, Clone)]
pub struct EncodeOptions {
    pub format: Format,
    pub level: i32,
    pub threads: u32,
    pub numeric_type: Option<NumericType>,
}
impl Default for EncodeOptions {
    fn default() -> Self {
        Self {
            format: Format::Zstd,
            level: 3,
            threads: 1,
            numeric_type: None,
        }
    }
}
#[derive(Debug, Clone)]
pub struct DecodeOptions {
    pub max_output: u64,
    pub max_window_log: u32,
    pub numeric_type: Option<NumericType>,
}
impl Default for DecodeOptions {
    fn default() -> Self {
        Self {
            max_output: 1024 * 1024 * 1024,
            max_window_log: 27,
            numeric_type: None,
        }
    }
}
#[derive(Debug, Clone, Copy, Default, Serialize)]
pub struct Stats {
    pub input_bytes: u64,
    pub output_bytes: u64,
}
pub fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}
