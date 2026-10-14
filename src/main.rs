use arqlet::{
    archive::{self, ArchiveLimits},
    archive_safety::ReadLimits,
    archive_sevenz, archive_zip, codecs, file_io, DecodeOptions, EncodeOptions, Format,
    NumericType,
};
use clap::{Parser, Subcommand, ValueEnum};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File},
    io::{self, Cursor, Read, Seek, Write},
    path::{Path, PathBuf},
    str::FromStr,
};

#[derive(Parser)]
#[command(
    name = "arqlet",
    version,
    about = "Compress, inspect, and unpack files with established formats",
    long_about = "Arqlet preserves input bytes using established compression and archive formats. It does not define a proprietary compression format. Resource limits apply to decoding and archive input; raise them only when needed.",
    after_help = "Examples:
  arqlet compress notes.txt --format zstd
  cat notes.txt | arqlet compress - -o notes.zst
  arqlet decompress notes.zst -o restored-notes.txt
  arqlet compress samples.f64le --format pco --type f64
  arqlet pack ./folder -o folder.tar.zst
  arqlet unpack folder.tar.zst --output ./restored

Decode output, archive input, entry-count, and depth caps are configurable. See each subcommand's help for defaults and format-specific limits."
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}
#[derive(Clone, Copy, ValueEnum)]
enum Preset {
    Fast,
    Balanced,
    Compact,
}
#[derive(Clone, Copy, ValueEnum)]
enum Fmt {
    Zstd,
    Gzip,
    Lz4,
    Pco,
}
#[derive(Clone, Copy, ValueEnum, PartialEq, Eq)]
enum ArchiveFmt {
    Zstd,
    Gzip,
    Lz4,
    Pco,
    Zip,
    #[value(name = "7z", alias = "sevenz")]
    Sevenz,
}
#[derive(Clone, Copy, PartialEq, Eq)]
enum ArchiveKind {
    Zip,
    Sevenz,
    Rar,
}
impl From<Fmt> for Format {
    fn from(f: Fmt) -> Self {
        match f {
            Fmt::Zstd => Self::Zstd,
            Fmt::Gzip => Self::Gzip,
            Fmt::Lz4 => Self::Lz4,
            Fmt::Pco => Self::Pco,
        }
    }
}
#[derive(Subcommand)]
enum Command {
    /// Compress a byte stream as Zstandard, gzip, LZ4, or typed Pco.
    #[command(
        long_about = "Compress a file or stdin. Output defaults to INPUT with the selected format suffix; use -o - to write stdout. Pco requires an explicit numeric --type (i32, u32, i64, u64, f32, or f64). Examples: `arqlet compress input.bin --format zstd`; `cat values.f64le | arqlet compress - -o values.pco --format pco --type f64`."
    )]
    Compress {
        /// Input file path, or `-` for stdin.
        input: String,
        #[arg(short, long, help = "Output path; use `-` for stdout")]
        output: Option<PathBuf>,
        #[arg(long, value_enum, default_value = "zstd", help = "Output codec")]
        format: Fmt,
        #[arg(
            long,
            value_enum,
            default_value = "balanced",
            help = "Preset used when --level is omitted"
        )]
        preset: Preset,
        #[arg(long, help = "Codec-specific compression level; overrides --preset")]
        level: Option<i32>,
        #[arg(
            long,
            help = "Zstandard worker threads (1..256; 0 selects available parallelism)",
            default_value_t = 1
        )]
        threads: u32,
        #[arg(
            long = "type",
            help = "Required for Pco: i32, u32, i64, u64, f32, or f64"
        )]
        numeric_type: Option<String>,
        #[arg(long)]
        force: bool,
        #[arg(long)]
        quiet: bool,
    },
    /// Decompress a supported stream to a file or stdout.
    #[command(
        long_about = "Decode Zstandard, gzip, LZ4, or Pco streams. Pco requires the matching --type. The default maximum decoded output is 1 GiB; --max-output changes that cap. Examples: `arqlet decompress input.zst`; `cat input.gz | arqlet decompress - -o -`."
    )]
    Decompress {
        /// Compressed file path, or `-` for stdin.
        input: String,
        #[arg(short, long, help = "Output path; use `-` for stdout")]
        output: Option<PathBuf>,
        #[arg(
            long = "type",
            help = "Required for Pco and must match the encoded numeric type"
        )]
        numeric_type: Option<String>,
        #[arg(
            long,
            help = "Maximum decoded output bytes (default: 1 GiB)",
            default_value_t = 1_073_741_824
        )]
        max_output: u64,
        #[arg(
            long,
            help = "Maximum Zstandard window log (default: 27)",
            default_value_t = 27
        )]
        max_window_log: u32,
        #[arg(long)]
        force: bool,
        #[arg(long)]
        quiet: bool,
    },
    /// Decode and validate a stream or supported archive.
    #[command(
        long_about = "Read the full stream and validate its decoding/checksums without writing extracted output. The default decoded output cap is 1 GiB; archive dictionary and header caps are separate. Example: `arqlet test backup.7z`."
    )]
    Test {
        /// Stream or archive path, or `-` for stdin.
        input: String,
        #[arg(
            long,
            help = "Maximum 7z dictionary allocation in bytes (default: 128 MiB)",
            default_value_t = 134_217_728
        )]
        max_dictionary: u64,
        #[arg(
            long,
            help = "Maximum archive header bytes (default: 16 MiB)",
            default_value_t = 16_777_216
        )]
        max_header: u64,

        #[arg(
            long = "type",
            help = "Required for Pco and must match the encoded numeric type"
        )]
        numeric_type: Option<String>,
        #[arg(
            long,
            help = "Maximum decoded output bytes (default: 1 GiB)",
            default_value_t = 1_073_741_824
        )]
        max_output: u64,
        #[arg(
            long,
            help = "Maximum Zstandard window log (default: 27)",
            default_value_t = 27
        )]
        max_window_log: u32,
    },
    /// Report detected format and available metadata.
    #[command(
        long_about = "Inspect stream or archive metadata. Stream sizes may be unknown, and inspection does not validate stream integrity. Archive input spooling, dictionary, and header caps are format-specific. Example: `arqlet info backup.zip --json`."
    )]
    Info {
        /// Stream or archive path, or `-` for stdin.
        input: String,
        #[arg(
            long,
            help = "Maximum 7z dictionary allocation in bytes (default: 128 MiB)",
            default_value_t = 134_217_728
        )]
        max_dictionary: u64,
        #[arg(
            long,
            help = "Maximum archive header bytes (default: 16 MiB)",
            default_value_t = 16_777_216
        )]
        max_header: u64,

        #[arg(long, help = "Print JSON output")]
        json: bool,
    },
    /// Compute a SHA-256 checksum of a file or stdin.
    #[command(
        long_about = "Compute SHA-256 over the complete input without modifying it. Use `-` to read stdin. Example: `arqlet checksum archive.7z`."
    )]
    Checksum {
        /// File path, or `-` for stdin.
        input: String,
        #[arg(long, help = "Print JSON output")]
        json: bool,
    },
    /// Pack a directory using tar, ZIP, or 7z.
    #[command(
        long_about = "Pack a directory with tar plus Zstandard/gzip/LZ4, or with ZIP/7z. Pco is a typed numeric stream and cannot encode directory archives. The default input/output byte cap is 1 GiB. Example: `arqlet pack ./project --format zip -o project.zip`."
    )]
    Pack {
        /// Directory whose regular files and directories will be archived.
        directory: PathBuf,
        #[arg(long, conflicts_with = "no_solid", help = "Use solid 7z compression")]
        solid: bool,
        #[arg(long, help = "Disable solid 7z compression")]
        no_solid: bool,
        #[arg(long, help = "7z dictionary size in MiB")]
        dictionary: Option<u32>,
        #[arg(long, help = "Store ZIP entries without compression")]
        stored: bool,
        #[arg(short, long, help = "Archive output path")]
        output: Option<PathBuf>,
        #[arg(long, value_enum, default_value = "zstd", help = "Archive format")]
        format: ArchiveFmt,
        #[arg(
            long,
            value_enum,
            default_value = "balanced",
            help = "Compression preset where applicable"
        )]
        preset: Preset,
        #[arg(long, help = "Codec-specific compression level")]
        level: Option<i32>,
        #[arg(
            long,
            help = "Zstandard worker threads; 0 selects available parallelism",
            default_value_t = 1
        )]
        threads: u32,
        #[arg(long, help = "Use stable entry ordering and timestamps")]
        deterministic: bool,
        #[arg(
            long,
            help = "Maximum archive entries (default: 100,000)",
            default_value_t = 100_000
        )]
        max_entries: u64,
        #[arg(
            long,
            help = "Maximum packed or unpacked file bytes (default: 1 GiB)",
            default_value_t = 1_073_741_824
        )]
        max_output: u64,
        #[arg(long, help = "Maximum path depth (default: 64)", default_value_t = 64)]
        max_depth: usize,
        #[arg(long)]
        force: bool,
        #[arg(long)]
        quiet: bool,
    },
    /// Safely unpack a supported tar stream, ZIP, or 7z archive.
    #[command(
        long_about = "Unpack into a new destination directory. Existing destinations are rejected. Entry-count, depth, decoded-byte, compressed-input, dictionary, and header limits vary by archive format. Directory publication moves children one at a time and rolls back moved children after an error; it is not atomic. Example: `arqlet unpack project.zip --output ./project-restored`."
    )]
    Unpack {
        input: String,
        #[arg(
            long,
            help = "Maximum 7z dictionary allocation in bytes (default: 128 MiB)",
            default_value_t = 134_217_728
        )]
        max_dictionary: u64,
        #[arg(
            long,
            help = "Maximum archive header bytes (default: 16 MiB)",
            default_value_t = 16_777_216
        )]
        max_header: u64,

        #[arg(
            short,
            long,
            required = true,
            help = "New destination directory (must not already exist)"
        )]
        output: PathBuf,
        #[arg(
            long = "type",
            help = "Required for Pco streams and must match the encoded numeric type"
        )]
        numeric_type: Option<String>,
        #[arg(
            long,
            help = "Maximum decoded output bytes (default: 1 GiB)",
            default_value_t = 1_073_741_824
        )]
        max_output: u64,
        #[arg(
            long,
            help = "Maximum archive entries (default: 100,000)",
            default_value_t = 100_000
        )]
        max_entries: u64,
        #[arg(long, help = "Maximum path depth (default: 64)", default_value_t = 64)]
        max_depth: usize,
    },
}
fn opts(
    format: Format,
    preset: Preset,
    level: Option<i32>,
    threads: u32,
    nt: Option<NumericType>,
) -> io::Result<EncodeOptions> {
    let auto = std::thread::available_parallelism()
        .map(usize::from)
        .unwrap_or(1)
        .min(256) as u32;
    let level = level.unwrap_or(match (format, preset) {
        (Format::Zstd, Preset::Fast) => 1,
        (Format::Zstd, Preset::Balanced) => 3,
        (Format::Zstd, Preset::Compact) => 9,
        (Format::Gzip, Preset::Fast) => 1,
        (Format::Gzip, Preset::Balanced) => 6,
        (Format::Gzip, Preset::Compact) => 9,
        (Format::Lz4, _) => 0,
        (Format::Pco, Preset::Fast) => 0,
        (Format::Pco, Preset::Balanced) => 4,
        (Format::Pco, Preset::Compact) => 8,
    });
    let o = EncodeOptions {
        format,
        level,
        threads: if threads == 0 { auto } else { threads },
        numeric_type: nt,
    };
    if o.threads > 256 {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "threads must be 0..256",
        ));
    }
    match format {
        Format::Zstd if !(1..=22).contains(&level) => return Err(bad("zstd level must be 1..22")),
        Format::Gzip if !(0..=9).contains(&level) => return Err(bad("gzip level must be 0..9")),
        Format::Lz4 if level != 0 => return Err(bad("lz4 supports level 0 only")),
        Format::Pco if !(0..=12).contains(&level) => return Err(bad("pco level must be 0..12")),
        _ => {}
    }
    if format != Format::Zstd && o.threads != 1 {
        return Err(bad("only zstd supports multiple threads"));
    }
    if (format == Format::Pco) != nt.is_some() {
        return Err(bad("--type is required only for pco"));
    }
    Ok(o)
}
fn bad(s: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, s)
}
fn nt(s: Option<String>) -> io::Result<Option<NumericType>> {
    s.map(|x| NumericType::from_str(&x).map_err(|e| bad(&e)))
        .transpose()
}
fn input(s: &str) -> io::Result<Box<dyn Read>> {
    if s == "-" {
        Ok(Box::new(io::stdin()))
    } else {
        Ok(Box::new(File::open(s)?))
    }
}
fn suffix_output(input: &str, ext: &str) -> Option<PathBuf> {
    if input == "-" {
        return None;
    }
    let p = Path::new(input);
    let mut os = p.as_os_str().to_os_string();
    os.push(format!(".{ext}"));
    Some(PathBuf::from(os))
}
fn decode_output(input: &str) -> Option<PathBuf> {
    if input == "-" {
        return None;
    }
    let p = Path::new(input);
    let name = p.file_name()?.to_string_lossy();
    let stem = [".zst", ".gz", ".lz4", ".pco"]
        .iter()
        .find_map(|s| name.strip_suffix(s));
    let mut out = p.to_path_buf();
    if let Some(stem) = stem {
        out.set_file_name(stem)
    } else {
        out.set_file_name(format!("{name}.decoded"))
    }
    Some(out)
}
fn run() -> io::Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Compress {
            input: src,
            output,
            format,
            preset,
            level,
            threads,
            numeric_type,
            force,
            quiet,
        } => {
            let o = opts(format.into(), preset, level, threads, nt(numeric_type)?)?;
            let mut r = input(&src)?;
            let out = output
                .or_else(|| suffix_output(&src, o.format.extension()))
                .filter(|p| p != Path::new("-"));
            let st = if let Some(p) = out {
                file_io::atomic_output(
                    &p,
                    if src == "-" {
                        None
                    } else {
                        Some(Path::new(&src))
                    },
                    force,
                    |f| codecs::compress(&mut r, f, &o),
                )?
            } else {
                codecs::compress(&mut r, io::stdout().lock(), &o)?
            };
            stats("compressed", st, quiet)
        }
        Command::Decompress {
            input: src,
            output,
            numeric_type,
            max_output,
            max_window_log,
            force,
            quiet,
        } => {
            let o = DecodeOptions {
                max_output,
                max_window_log,
                numeric_type: nt(numeric_type)?,
            };
            let mut r = input(&src)?;
            let out = output
                .or_else(|| decode_output(&src))
                .filter(|p| p != Path::new("-"));
            let st = if let Some(p) = out {
                file_io::atomic_output(
                    &p,
                    if src == "-" {
                        None
                    } else {
                        Some(Path::new(&src))
                    },
                    force,
                    |f| codecs::decompress(&mut r, f, &o),
                )?
            } else {
                codecs::decompress(&mut r, io::stdout().lock(), &o)?
            };
            stats("decompressed", st, quiet)
        }
        Command::Test {
            input: src,
            numeric_type,
            max_output,
            max_window_log,
            max_dictionary,
            max_header,
        } => {
            let (kind, _prefix, source) = probe_input(&src)?;
            if let Some(kind) = kind {
                if nt(numeric_type)?.is_some() {
                    return Err(bad("numeric type is invalid for archives"));
                }
                let limits = ReadLimits {
                    archive: ArchiveLimits {
                        max_total_bytes: max_output,
                        ..ArchiveLimits::default()
                    },
                    max_dictionary_bytes: max_dictionary,
                    max_header_bytes: max_header,
                    ..ReadLimits::default()
                };
                let st = with_archive_input(&src, source, &limits, |path| match kind {
                    ArchiveKind::Zip => archive_zip::test(path, &limits),
                    ArchiveKind::Sevenz => archive_sevenz::test(path, &limits),
                    ArchiveKind::Rar => Err(bad(
                        "RAR decoding is not integrated; use an installed UnRAR or 7-Zip tool",
                    )),
                })?;
                stats("valid", st, false);
            } else {
                let o = DecodeOptions {
                    max_output,
                    max_window_log,
                    numeric_type: nt(numeric_type)?,
                };
                let st = codecs::decompress(source, io::sink(), &o)?;
                stats("valid", st, false);
            }
        }
        Command::Info {
            input: src,
            json,
            max_dictionary,
            max_header,
        } => {
            let (kind, prefix, source) = probe_input(&src)?;
            if let Some(kind) = kind {
                let limits = ReadLimits {
                    max_dictionary_bytes: max_dictionary,
                    max_header_bytes: max_header,
                    ..ReadLimits::default()
                };
                let data = if kind == ArchiveKind::Rar {
                    serde_json::json!({"format":"rar","supported":false,"integrity_validated":false,"reason":"RAR extraction is available through external UnRAR/7-Zip, not integrated into Arqlet"})
                } else {
                    with_archive_input(&src, source, &limits, |path| match kind {
                        ArchiveKind::Zip => archive_zip::info(path, &limits),
                        ArchiveKind::Sevenz => archive_sevenz::info(path, &limits),
                        ArchiveKind::Rar => unreachable!(),
                    })?
                };
                if json {
                    println!(
                        "{}",
                        serde_json::to_string(&data).map_err(io::Error::other)?
                    );
                } else {
                    println!(
                        "{}",
                        serde_json::to_string_pretty(&data).map_err(io::Error::other)?
                    );
                }
            } else {
                let f = codecs::detect_format(&prefix)?;
                let size = if src == "-" {
                    None
                } else {
                    fs::metadata(&src).ok().map(|m| m.len())
                };
                if json {
                    println!(
                        "{}",
                        serde_json::json!({"format":format!("{f:?}"),"compressed_bytes":size,"uncompressed_bytes":null,"integrity_validated":false})
                    );
                } else {
                    println!("format: {f:?}\ncompressed bytes: {}\nuncompressed bytes: unknown\nintegrity validated: no",size.map_or("unknown".into(),|v|v.to_string()));
                }
            }
        }
        Command::Checksum { input: src, json } => {
            let mut r = input(&src)?;
            let mut h = Sha256::new();
            let mut b = [0; 65536];
            loop {
                let n = r.read(&mut b)?;
                if n == 0 {
                    break;
                }
                h.update(&b[..n])
            }
            let hex: String = h.finalize().iter().map(|b| format!("{b:02x}")).collect();
            if json {
                println!(
                    "{{\"sha256\":\"{hex}\",\"filename\":{}}}",
                    serde_json::to_string(&src).unwrap()
                )
            } else {
                println!("{hex}  {}", src.replace('\n', "\\n"))
            }
        }
        Command::Pack {
            directory,
            output,
            format,
            preset,
            level,
            threads,
            deterministic,
            max_entries,
            max_output,
            max_depth,
            force,
            quiet,
            solid,
            no_solid,
            dictionary,
            stored,
        } => {
            if format != ArchiveFmt::Sevenz && (solid || no_solid || dictionary.is_some()) {
                return Err(bad("solid/dictionary options require --format 7z"));
            }
            if format != ArchiveFmt::Zip && stored {
                return Err(bad("--stored requires --format zip"));
            }
            let limits = ArchiveLimits {
                max_entries,
                max_total_bytes: max_output,
                max_depth,
                deterministic,
            };
            let is_container = matches!(format, ArchiveFmt::Zip | ArchiveFmt::Sevenz);
            let suffix = match format {
                ArchiveFmt::Zip => "zip",
                ArchiveFmt::Sevenz => "7z",
                ArchiveFmt::Zstd => "tar.zst",
                ArchiveFmt::Gzip => "tar.gz",
                ArchiveFmt::Lz4 => "tar.lz4",
                ArchiveFmt::Pco => return Err(bad("Pco cannot encode directory archives")),
            };
            let p = output.unwrap_or_else(|| {
                let mut x = directory.as_os_str().to_os_string();
                x.push(format!(".{suffix}"));
                PathBuf::from(x)
            });
            let encode = |f: &mut File| -> io::Result<arqlet::Stats> {
                match format {
                    ArchiveFmt::Zip => {
                        if threads != 1 {
                            return Err(bad("ZIP supports one thread"));
                        }
                        let level = level.unwrap_or(match preset {
                            Preset::Fast => 1,
                            Preset::Balanced => 6,
                            Preset::Compact => 9,
                        });
                        archive_zip::pack(
                            &directory,
                            f,
                            &archive_zip::PackOptions { level, stored },
                            &limits,
                        )
                    }
                    ArchiveFmt::Sevenz => {
                        let level = level.unwrap_or(match preset {
                            Preset::Fast => 3,
                            Preset::Balanced => 5,
                            Preset::Compact => 7,
                        });
                        if !(0..=9).contains(&level) {
                            return Err(bad("7z level must be 0..9"));
                        }
                        archive_sevenz::pack(
                            &directory,
                            f,
                            &archive_sevenz::PackOptions {
                                level: level as u32,
                                solid: !no_solid,
                                dictionary_bytes: dictionary.unwrap_or(16_777_216),
                                threads,
                            },
                            &limits,
                        )
                    }
                    other => {
                        let byte = match other {
                            ArchiveFmt::Zstd => Format::Zstd,
                            ArchiveFmt::Gzip => Format::Gzip,
                            ArchiveFmt::Lz4 => Format::Lz4,
                            _ => unreachable!(),
                        };
                        let o = opts(byte, preset, level, threads, None)?;
                        archive::pack(&directory, f, &o, &limits)
                    }
                }
            };
            if p == Path::new("-") {
                if is_container {
                    let mut spool = tempfile::tempfile()?;
                    let st = encode(&mut spool)?;
                    spool.rewind()?;
                    io::copy(&mut spool, &mut io::stdout().lock())?;
                    stats("packed", st, quiet);
                } else {
                    let byte = match format {
                        ArchiveFmt::Zstd => Format::Zstd,
                        ArchiveFmt::Gzip => Format::Gzip,
                        ArchiveFmt::Lz4 => Format::Lz4,
                        _ => unreachable!(),
                    };
                    let o = opts(byte, preset, level, threads, None)?;
                    let st = archive::pack(&directory, io::stdout().lock(), &o, &limits)?;
                    stats("packed", st, quiet);
                }
                return Ok(());
            }
            let root = fs::canonicalize(&directory)?;
            let parent = p
                .parent()
                .filter(|x| !x.as_os_str().is_empty())
                .unwrap_or(Path::new("."));
            let cp = fs::canonicalize(parent)?.join(
                p.file_name()
                    .ok_or_else(|| bad("output requires filename"))?,
            );
            if root.is_dir() && cp.starts_with(&root) {
                return Err(bad("archive output cannot be inside input directory"));
            }
            let st = file_io::atomic_output(&p, Some(&directory), force, encode)?;
            stats("packed", st, quiet);
        }
        Command::Unpack {
            input: src,
            output,
            numeric_type,
            max_output,
            max_entries,
            max_depth,
            max_dictionary,
            max_header,
        } => {
            if nt(numeric_type)?.is_some() {
                return Err(bad("numeric type is invalid for archives"));
            }
            let limits = ArchiveLimits {
                max_entries,
                max_total_bytes: max_output,
                max_depth,
                deterministic: false,
            };
            let (kind, _prefix, source) = probe_input(&src)?;
            let st = if let Some(kind) = kind {
                let limits = ReadLimits {
                    archive: limits,
                    max_dictionary_bytes: max_dictionary,
                    max_header_bytes: max_header,
                    ..ReadLimits::default()
                };
                with_archive_input(&src, source, &limits, |path| match kind {
                    ArchiveKind::Zip => archive_zip::unpack(path, &output, &limits),
                    ArchiveKind::Sevenz => archive_sevenz::unpack(path, &output, &limits),
                    ArchiveKind::Rar => Err(bad(
                        "RAR decoding is not integrated; use an installed UnRAR or 7-Zip tool",
                    )),
                })?
            } else {
                archive::unpack(
                    source,
                    &output,
                    &DecodeOptions {
                        max_output,
                        max_window_log: 27,
                        numeric_type: None,
                    },
                    &limits,
                )?
            };
            stats("unpacked", st, false);
        }
    }
    Ok(())
}
fn stats(verb: &str, s: arqlet::Stats, quiet: bool) {
    if !quiet {
        eprintln!(
            "{verb}: {} input bytes, {} output bytes",
            s.input_bytes, s.output_bytes
        )
    }
}
fn main() {
    if let Err(e) = run() {
        if e.kind() != io::ErrorKind::BrokenPipe {
            eprintln!("arqlet: {e}")
        }
        std::process::exit(1)
    }
}

type ProbedInput = (Option<ArchiveKind>, Vec<u8>, Box<dyn Read>);
fn probe_input(src: &str) -> io::Result<ProbedInput> {
    let mut source = input(src)?;
    let mut prefix = vec![0; 8];
    let mut used = 0;
    while used < prefix.len() {
        match source.read(&mut prefix[used..]) {
            Ok(0) => break,
            Ok(n) => used += n,
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            Err(e) => return Err(e),
        }
    }
    prefix.truncate(used);
    let kind = if prefix.starts_with(b"PK\x03\x04")
        || prefix.starts_with(b"PK\x05\x06")
        || prefix.starts_with(b"PK\x07\x08")
    {
        Some(ArchiveKind::Zip)
    } else if prefix.starts_with(&[0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c]) {
        Some(ArchiveKind::Sevenz)
    } else if prefix.starts_with(b"Rar!\x1a\x07") {
        Some(ArchiveKind::Rar)
    } else {
        None
    };
    Ok((
        kind,
        prefix.clone(),
        Box::new(Cursor::new(prefix).chain(source)),
    ))
}
fn with_archive_input<T>(
    src: &str,
    source: Box<dyn Read>,
    limits: &ReadLimits,
    consume: impl FnOnce(&Path) -> io::Result<T>,
) -> io::Result<T> {
    if src != "-" {
        return consume(Path::new(src));
    }
    let mut spool = tempfile::NamedTempFile::new()?;
    let cap = limits
        .max_compressed_bytes
        .checked_add(1)
        .ok_or_else(|| bad("archive input limit overflow"))?;
    let n = io::copy(&mut source.take(cap), spool.as_file_mut())?;
    if n > limits.max_compressed_bytes {
        return Err(bad("compressed archive exceeds input limit"));
    }
    spool.as_file_mut().flush()?;
    consume(spool.path())
}
