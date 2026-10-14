use bytepleat::{
    archive,
    archive_safety::{self, ReadLimits},
    archive_sevenz, archive_zip, DecodeOptions, EncodeOptions, Format,
};
use serde::{Deserialize, Serialize};
use std::{
    ffi::OsString,
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    path::{Path, PathBuf},
};

const DEFAULT_LIMIT: u64 = 1024 * 1024 * 1024;
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum ArchiveFormat {
    #[serde(rename = "zip")]
    Zip,
    #[serde(rename = "7z")]
    Sevenz,
    #[serde(rename = "tar.zst")]
    TarZst,
    #[serde(rename = "tar.gz")]
    TarGz,
    #[serde(rename = "tar.lz4")]
    TarLz4,
}
impl ArchiveFormat {
    fn label(self) -> &'static str {
        match self {
            Self::Zip => "zip",
            Self::Sevenz => "7z",
            Self::TarZst => "tar.zst",
            Self::TarGz => "tar.gz",
            Self::TarLz4 => "tar.lz4",
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct OperationRequest {
    pub action: String,
    pub inputs: Vec<PathBuf>,
    pub destination: Option<PathBuf>,
    pub format: Option<ArchiveFormat>,
    #[serde(default)]
    pub selected_entries: Vec<String>,
    #[serde(default = "limit")]
    pub max_output_bytes: u64,
}
fn limit() -> u64 {
    DEFAULT_LIMIT
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ArchiveEntry {
    pub name: String,
    pub size: u64,
    pub is_dir: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ArchiveListing {
    pub format: String,
    pub entries: Vec<ArchiveEntry>,
    pub total_bytes: u64,
    pub integrity_validated: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Progress {
    pub phase: String,
    pub processed_bytes: u64,
    pub total_bytes: Option<u64>,
    pub message: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct WorkerResult {
    pub output_kind: String,
    pub input_bytes: u64,
    pub output_bytes: u64,
    pub message: String,
}
fn limits(n: u64) -> ReadLimits {
    let mut l = ReadLimits::default();
    l.archive.max_total_bytes = n;
    l.max_compressed_bytes = n;
    l
}
fn ioerr(e: impl ToString) -> String {
    e.to_string()
}
fn detect(p: &Path) -> io::Result<ArchiveFormat> {
    let mut f = File::open(p)?;
    let mut b = [0; 8];
    let n = f.read(&mut b)?;
    let x = &b[..n];
    if x.starts_with(b"PK\x03\x04") || x.starts_with(b"PK\x05\x06") {
        Ok(ArchiveFormat::Zip)
    } else if x.starts_with(b"7z\xbc\xaf\x27\x1c") {
        Ok(ArchiveFormat::Sevenz)
    } else if x.starts_with(&[0x1f, 0x8b]) {
        Ok(ArchiveFormat::TarGz)
    } else if x.starts_with(&[0x04, 0x22, 0x4d, 0x18]) {
        Ok(ArchiveFormat::TarLz4)
    } else if x.starts_with(&[0x28, 0xb5, 0x2f, 0xfd]) {
        Ok(ArchiveFormat::TarZst)
    } else {
        Err(bytepleat::invalid(
            "unsupported or unrecognized archive format",
        ))
    }
}
pub fn inspect_archive(path: &Path, max_output_bytes: u64) -> Result<ArchiveListing, String> {
    let f = detect(path).map_err(ioerr)?;
    let l = limits(max_output_bytes);
    if matches!(f, ArchiveFormat::Zip) {
        let validated_handle =
            same_file::Handle::from_file(File::open(path).map_err(ioerr)?).map_err(ioerr)?;
        let before = fs::metadata(path).map_err(ioerr)?;
        archive_zip::info(path, &l).map_err(ioerr)?;
        let checked = fs::metadata(path).map_err(ioerr)?;
        if before.len() != checked.len() || before.modified().ok() != checked.modified().ok() {
            return Err("ZIP input changed during bounded header preflight".into());
        }
        let file = File::open(path).map_err(ioerr)?;
        let index_handle =
            same_file::Handle::from_file(file.try_clone().map_err(ioerr)?).map_err(ioerr)?;
        if validated_handle != index_handle {
            return Err("ZIP input was replaced after bounded header preflight".into());
        }
        let mut z = zip::ZipArchive::new(file).map_err(ioerr)?;
        let mut policy = archive_safety::EntryPolicy::default();
        let mut entries = Vec::new();
        for i in 0..z.len() {
            let e = z.by_index(i).map_err(ioerr)?;
            let d = e.is_dir();
            let name = policy
                .add(&e.name().map_err(ioerr)?, d, e.size(), &l.archive)
                .map_err(ioerr)?;
            entries.push(ArchiveEntry {
                name,
                size: e.size(),
                is_dir: d,
            });
        }
        let after = fs::metadata(path).map_err(ioerr)?;
        if checked.len() != after.len() || checked.modified().ok() != after.modified().ok() {
            return Err("ZIP input changed while its index was read".into());
        }
        return Ok(ArchiveListing {
            format: f.label().into(),
            entries,
            total_bytes: policy.total_bytes(),
            integrity_validated: false,
        });
    }
    if f == ArchiveFormat::Sevenz {
        let v = archive_sevenz::info(path, &l).map_err(ioerr)?;
        let entries = v["files"]
            .as_array()
            .ok_or("7z metadata has no file list")?
            .iter()
            .map(|x| {
                Ok(ArchiveEntry {
                    name: x["name"].as_str().ok_or("invalid 7z name")?.to_owned(),
                    size: x["size"].as_u64().ok_or("invalid 7z size")?,
                    is_dir: x["type"].as_str() == Some("directory"),
                })
            })
            .collect::<Result<Vec<_>, &str>>()?;
        return Ok(ArchiveListing {
            format: f.label().into(),
            total_bytes: entries.iter().map(|x| x.size).sum(),
            entries,
            integrity_validated: false,
        });
    }
    let temp = tempfile::tempdir().map_err(ioerr)?;
    let decoded = temp.path().join("decoded");
    archive::unpack(
        File::open(path).map_err(ioerr)?,
        &decoded,
        &DecodeOptions {
            max_output: max_output_bytes,
            ..DecodeOptions::default()
        },
        &l.archive,
    )
    .map_err(ioerr)?;
    let mut entries = Vec::new();
    for e in walkdir::WalkDir::new(&decoded).min_depth(1) {
        let e = e.map_err(ioerr)?;
        let m = e.metadata().map_err(ioerr)?;
        entries.push(ArchiveEntry {
            name: e
                .path()
                .strip_prefix(&decoded)
                .map_err(ioerr)?
                .to_string_lossy()
                .replace('\\', "/"),
            size: if m.is_file() { m.len() } else { 0 },
            is_dir: m.is_dir(),
        });
    }
    let total_bytes = entries.iter().map(|x| x.size).sum();
    Ok(ArchiveListing {
        format: f.label().into(),
        entries,
        total_bytes,
        integrity_validated: false,
    })
}

pub fn execute(
    r: &OperationRequest,
    stage: &Path,
    progress: impl Fn(Progress),
) -> Result<WorkerResult, String> {
    if r.max_output_bytes == 0 || r.max_output_bytes > DEFAULT_LIMIT {
        return Err("output limit must be between 1 byte and 1 GiB".into());
    }
    if r.inputs.is_empty() {
        return Err("at least one input is required".into());
    }
    let l = limits(r.max_output_bytes);
    match r.action.as_str() {
        "create" => {
            let fmt = r.format.ok_or("create requires format")?;
            if r.destination.is_none() {
                return Err("create requires destination".into());
            }
            validate_create_paths(r)?;
            let base = stage.join("sources");
            fs::create_dir(&base).map_err(ioerr)?;
            let mut bytes = 0u64;
            progress(Progress {
                phase: "preparing".into(),
                processed_bytes: 0,
                total_bytes: None,
                message: format!(
                    "Preparing {} selected input(s); copying a private snapshot",
                    r.inputs.len()
                ),
            });
            for input in &r.inputs {
                let md = fs::symlink_metadata(input).map_err(ioerr)?;
                if md.file_type().is_symlink() || !(md.is_file() || md.is_dir()) {
                    return Err("input must be a regular file or directory".into());
                }
                if r.inputs.len() == 1 && md.is_dir() {
                    copy_folder_contents(input, &base, &mut bytes, r.max_output_bytes)?;
                    continue;
                }
                let name = input
                    .file_name()
                    .and_then(|x| x.to_str())
                    .ok_or("input basename must be UTF-8")?;
                let dst = base.join(name);
                if md.is_dir() {
                    copy_tree(input, &dst, &mut bytes, r.max_output_bytes)?
                } else {
                    copy_file(input, &dst, &mut bytes, r.max_output_bytes)?
                }
            }
            progress(Progress {
                phase: "compressing".into(),
                processed_bytes: bytes,
                total_bytes: Some(bytes),
                message: "Compressing staged input bytes".into(),
            });
            let artifact = stage.join("artifact");
            let mut out = File::create(&artifact).map_err(ioerr)?;
            let st = match fmt {
                ArchiveFormat::Zip => archive_zip::pack(
                    &base,
                    &mut out,
                    &archive_zip::PackOptions::default(),
                    &l.archive,
                ),
                ArchiveFormat::Sevenz => archive_sevenz::pack(
                    &base,
                    &mut out,
                    &archive_sevenz::PackOptions {
                        level: 5,
                        solid: false,
                        dictionary_bytes: 16 * 1024 * 1024,
                        threads: 1,
                    },
                    &l.archive,
                ),
                _ => archive::pack(
                    &base,
                    &mut out,
                    &EncodeOptions {
                        format: match fmt {
                            ArchiveFormat::TarZst => Format::Zstd,
                            ArchiveFormat::TarGz => Format::Gzip,
                            _ => Format::Lz4,
                        },
                        level: if fmt == ArchiveFormat::TarLz4 { 0 } else { 3 },
                        ..EncodeOptions::default()
                    },
                    &l.archive,
                ),
            }
            .map_err(ioerr)?;
            out.sync_all().map_err(ioerr)?;
            progress(Progress {
                phase: "complete".into(),
                processed_bytes: st.input_bytes,
                total_bytes: Some(st.input_bytes),
                message: "archive created".into(),
            });
            Ok(WorkerResult {
                output_kind: "file".into(),
                input_bytes: st.input_bytes,
                output_bytes: fs::metadata(artifact).map_err(ioerr)?.len(),
                message: format!("Created {} archive", fmt.label()),
            })
        }
        "extract" | "test" => {
            if r.inputs.len() != 1 {
                return Err("extract and test accept one archive".into());
            }
            let path = &r.inputs[0];
            let fmt = detect(path).map_err(ioerr)?;
            let n = fs::metadata(path).map_err(ioerr)?.len();
            if n > r.max_output_bytes {
                return Err("archive input exceeds limit".into());
            }
            if r.action == "test" {
                let s = match fmt {
                    ArchiveFormat::Zip => archive_zip::test(path, &l).map_err(ioerr)?.output_bytes,
                    ArchiveFormat::Sevenz => {
                        archive_sevenz::test(path, &l).map_err(ioerr)?.output_bytes
                    }
                    _ => inspect_archive(path, r.max_output_bytes)?.total_bytes,
                };
                return Ok(WorkerResult {
                    output_kind: "none".into(),
                    input_bytes: n,
                    output_bytes: s,
                    message: "Integrity validated".into(),
                });
            }
            let decoded = stage.join("decoded");
            progress(Progress {
                phase: "decoding".into(),
                processed_bytes: 0,
                total_bytes: Some(n),
                message: "Decoding and validating archive".into(),
            });
            let s = match fmt {
                ArchiveFormat::Zip => archive_zip::unpack(path, &decoded, &l),
                ArchiveFormat::Sevenz => archive_sevenz::unpack(path, &decoded, &l),
                _ => archive::unpack(
                    File::open(path).map_err(ioerr)?,
                    &decoded,
                    &DecodeOptions {
                        max_output: r.max_output_bytes,
                        ..DecodeOptions::default()
                    },
                    &l.archive,
                ),
            }
            .map_err(ioerr)?;
            if !r.selected_entries.is_empty() {
                trim_selected(&decoded, &r.selected_entries)?
            }
            progress(Progress {
                phase: "complete".into(),
                processed_bytes: s.output_bytes,
                total_bytes: Some(s.output_bytes),
                message: "archive decoded and validated".into(),
            });
            Ok(WorkerResult {
                output_kind: "directory".into(),
                input_bytes: s.input_bytes,
                output_bytes: s.output_bytes,
                message: "Archive decoded and validated".into(),
            })
        }
        x => Err(format!("unsupported action: {x}")),
    }
}
fn copy_file(a: &Path, b: &Path, total: &mut u64, max: u64) -> Result<(), String> {
    let metadata = fs::symlink_metadata(a).map_err(ioerr)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err("input changed to a link or non-file".into());
    }
    let mut input = File::open(a).map_err(ioerr)?;
    let mut output = File::create_new(b).map_err(ioerr)?;
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let n = input.read(&mut buffer).map_err(ioerr)?;
        if n == 0 {
            break;
        }
        let new_total = total.checked_add(n as u64).ok_or("size overflow")?;
        if new_total > max {
            return Err("input exceeds output limit".into());
        }
        output.write_all(&buffer[..n]).map_err(ioerr)?;
        *total = new_total;
    }
    output.sync_all().map_err(ioerr)?;
    if fs::metadata(a).map_err(ioerr)?.len() != metadata.len() {
        return Err("source changed while staging".into());
    }
    Ok(())
}
fn copy_tree(a: &Path, b: &Path, total: &mut u64, max: u64) -> Result<(), String> {
    fs::create_dir(b).map_err(ioerr)?;
    for e in walkdir::WalkDir::new(a).min_depth(1).follow_links(false) {
        let e = e.map_err(ioerr)?;
        let ty = e.file_type();
        if !(ty.is_file() || ty.is_dir()) {
            return Err("symlink or special input rejected".into());
        }
        let rel = e.path().strip_prefix(a).map_err(ioerr)?;
        let dst = b.join(rel);
        if ty.is_dir() {
            fs::create_dir(&dst).map_err(ioerr)?
        } else {
            if !rel.to_str().is_some() {
                return Err("input path must be UTF-8".into());
            }
            copy_file(e.path(), &dst, total, max)?
        }
    }
    Ok(())
}
fn copy_folder_contents(a: &Path, b: &Path, total: &mut u64, max: u64) -> Result<(), String> {
    for ent in walkdir::WalkDir::new(a).min_depth(1).follow_links(false) {
        let e = ent.map_err(ioerr)?;
        let ty = e.file_type();
        if !(ty.is_file() || ty.is_dir()) {
            return Err("symlink or special input rejected".into());
        }
        let rel = e.path().strip_prefix(a).map_err(ioerr)?;
        let target = b.join(rel);
        if ty.is_dir() {
            fs::create_dir_all(target).map_err(ioerr)?
        } else {
            if !rel.to_str().is_some() {
                return Err("input path must be UTF-8".into());
            }
            if let Some(p) = target.parent() {
                fs::create_dir_all(p).map_err(ioerr)?
            }
            copy_file(e.path(), &target, total, max)?
        }
    }
    Ok(())
}
fn trim_selected(root: &Path, names: &[String]) -> Result<(), String> {
    let mut normalized = Vec::new();
    for raw in names {
        let name = archive_safety::normalize_name(raw, raw.ends_with('/')).map_err(ioerr)?;
        if normalized.contains(&name) {
            return Err("duplicate selected entry".into());
        }
        normalized.push(name)
    }
    let all: Vec<_> = walkdir::WalkDir::new(root)
        .min_depth(1)
        .into_iter()
        .map(|e| {
            e.map(|x| {
                x.path()
                    .strip_prefix(root)
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/")
            })
            .map_err(ioerr)
        })
        .collect::<Result<_, _>>()?;
    for name in &normalized {
        if !all.iter().any(|x| x == name) {
            return Err(format!("unknown selected entry: {name}"));
        }
    }
    for p in all.into_iter().rev() {
        if !normalized
            .iter()
            .any(|x| p == *x || p.starts_with(&format!("{x}/")))
        {
            let path = root.join(p);
            if path.is_dir() {
                let _ = fs::remove_dir(path);
            } else {
                fs::remove_file(path).map_err(ioerr)?;
            }
        }
    }
    Ok(())
}
fn validate_create_paths(r: &OperationRequest) -> Result<(), String> {
    let dest = r.destination.as_ref().ok_or("destination required")?;
    let parent = dest
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let dest_abs = fs::canonicalize(parent)
        .map_err(ioerr)?
        .join(dest.file_name().ok_or("destination requires filename")?);
    let mut identities = Vec::new();
    let mut names = std::collections::HashSet::new();
    for input in &r.inputs {
        let canonical = fs::canonicalize(input).map_err(ioerr)?;
        if identities
            .iter()
            .any(|x: &PathBuf| same_file::is_same_file(x, &canonical).unwrap_or(false))
        {
            return Err("duplicate input alias".into());
        }
        if identities
            .iter()
            .any(|x: &PathBuf| canonical.starts_with(x) || x.starts_with(&canonical))
        {
            return Err("selected input roots overlap".into());
        }
        let md = fs::symlink_metadata(input).map_err(ioerr)?;
        if dest_abs.starts_with(&canonical) || (md.is_file() && dest_abs == canonical) {
            return Err("output aliases or is inside an input".into());
        }
        let name = input
            .file_name()
            .and_then(|x| x.to_str())
            .ok_or("input basename must be UTF-8")?;
        let name = archive_safety::normalize_name(name, md.is_dir()).map_err(ioerr)?;
        use unicode_normalization::UnicodeNormalization;
        let portable_key = name
            .nfc()
            .collect::<String>()
            .to_lowercase()
            .nfc()
            .collect::<String>();
        if !names.insert(portable_key) {
            return Err("input basenames collide portably".into());
        }
        identities.push(canonical);
    }
    Ok(())
}
pub fn publish(
    r: &OperationRequest,
    stage: &Path,
    result: &WorkerResult,
) -> Result<Option<PathBuf>, String> {
    if result.output_kind == "none" {
        return Ok(None);
    }
    let dest = r.destination.as_ref().ok_or("destination required")?;
    if fs::symlink_metadata(dest).is_ok() {
        return Err("destination already exists".into());
    }
    let src = stage.join(if result.output_kind == "file" {
        "artifact"
    } else {
        "decoded"
    });
    if result.output_kind == "file" {
        File::open(&src).and_then(|f| f.sync_all()).map_err(ioerr)?;
    }
    rename_noreplace(&src, dest).map_err(ioerr)?;
    Ok(Some(dest.clone()))
}

#[cfg(target_os = "linux")]
fn rename_noreplace(from: &Path, to: &Path) -> io::Result<()> {
    use std::{ffi::CString, os::unix::ffi::OsStrExt};
    let from = CString::new(from.as_os_str().as_bytes())
        .map_err(|_| bytepleat::invalid("source path contains NUL"))?;
    let to = CString::new(to.as_os_str().as_bytes())
        .map_err(|_| bytepleat::invalid("destination path contains NUL"))?;
    unsafe extern "C" {
        fn renameat2(
            olddirfd: i32,
            oldpath: *const std::ffi::c_char,
            newdirfd: i32,
            newpath: *const std::ffi::c_char,
            flags: u32,
        ) -> i32;
    }
    // RENAME_NOREPLACE makes the publication atomic and fails if any destination exists.
    let rc = unsafe { renameat2(-100, from.as_ptr(), -100, to.as_ptr(), 1) };
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}
#[cfg(target_os = "macos")]
fn rename_noreplace(from: &Path, to: &Path) -> io::Result<()> {
    use std::{ffi::CString, os::unix::ffi::OsStrExt};
    let from = CString::new(from.as_os_str().as_bytes())
        .map_err(|_| bytepleat::invalid("source path contains NUL"))?;
    let to = CString::new(to.as_os_str().as_bytes())
        .map_err(|_| bytepleat::invalid("destination path contains NUL"))?;
    unsafe extern "C" {
        fn renamex_np(
            from: *const std::ffi::c_char,
            to: *const std::ffi::c_char,
            flags: u32,
        ) -> i32;
    }
    // RENAME_EXCL makes renamex_np fail atomically if the destination exists.
    let rc = unsafe { renamex_np(from.as_ptr(), to.as_ptr(), 4) };
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}
#[cfg(target_os = "windows")]
fn rename_noreplace(from: &Path, to: &Path) -> io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    let from: Vec<u16> = from.as_os_str().encode_wide().chain(Some(0)).collect();
    let to: Vec<u16> = to.as_os_str().encode_wide().chain(Some(0)).collect();
    unsafe extern "system" {
        fn MoveFileW(from: *const u16, to: *const u16) -> i32;
    }
    let rc = unsafe { MoveFileW(from.as_ptr(), to.as_ptr()) };
    if rc != 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}
#[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
fn rename_noreplace(from: &Path, to: &Path) -> io::Result<()> {
    let _ = (from, to);
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "exclusive rename publication is unsupported on this platform",
    ))
}

#[derive(Serialize, Deserialize)]
struct CliRequest {
    request: OperationRequest,
    staging: PathBuf,
}
#[derive(Serialize, Deserialize)]
struct CliResult {
    ok: bool,
    result: Option<WorkerResult>,
    error: Option<String>,
}
pub fn run_worker_cli(args: &[OsString]) -> Option<i32> {
    if args.len() != 4 || args[0] != "--desktop-worker" {
        return None;
    }
    let request_path = PathBuf::from(&args[1]);
    let result_path = PathBuf::from(&args[2]);
    let progress_path = PathBuf::from(&args[3]);
    let answer = (|| {
        let m = fs::metadata(&request_path)?;
        if m.len() > 1024 * 1024 {
            return Err(bytepleat::invalid("request too large"));
        }
        let b = fs::read(&request_path)?;
        let req: CliRequest =
            serde_json::from_slice(&b).map_err(|e| bytepleat::invalid(e.to_string()))?;
        write_atomic_json(
            &progress_path,
            &Progress {
                phase: "starting".into(),
                processed_bytes: 0,
                total_bytes: None,
                message: "worker started".into(),
            },
        )?;
        let last = std::sync::Mutex::new(Progress {
            phase: "starting".into(),
            processed_bytes: 0,
            total_bytes: None,
            message: "worker started".into(),
        });
        let progress_error = std::sync::Mutex::new(None);
        let result = execute(&req.request, &req.staging, |p| {
            *last.lock().unwrap() = p;
            if let Err(e) = write_atomic_json(&progress_path, &*last.lock().unwrap()) {
                *progress_error.lock().unwrap() = Some(e.to_string());
            }
        });
        if let Some(e) = progress_error.into_inner().unwrap() {
            return Err(bytepleat::invalid(e));
        }
        Ok(result)
    })();
    let output = match answer {
        Ok(Ok(result)) => CliResult {
            ok: true,
            result: Some(result),
            error: None,
        },
        Ok(Err(error)) => CliResult {
            ok: false,
            result: None,
            error: Some(error),
        },
        Err(e) => CliResult {
            ok: false,
            result: None,
            error: Some(e.to_string()),
        },
    };
    if write_atomic_json(&result_path, &output).is_err() {
        return Some(1);
    }
    Some(if output.ok { 0 } else { 1 })
}
fn write_atomic_json(path: &Path, value: &impl Serialize) -> io::Result<()> {
    static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let tmp = path.with_extension(format!(
        "{}.{}.tmp",
        std::process::id(),
        NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
    ));
    let bytes = serde_json::to_vec(value).map_err(|e| bytepleat::invalid(e.to_string()))?;
    let mut file = OpenOptions::new().write(true).create_new(true).open(&tmp)?;
    file.write_all(&bytes)?;
    file.sync_all()?;
    drop(file);
    if let Err(e) = fs::rename(&tmp, path) {
        let _ = fs::remove_file(&tmp);
        return Err(e);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(
        action: &str,
        inputs: Vec<PathBuf>,
        dest: Option<PathBuf>,
        format: Option<ArchiveFormat>,
    ) -> OperationRequest {
        OperationRequest {
            action: action.into(),
            inputs,
            destination: dest,
            format,
            selected_entries: Vec::new(),
            max_output_bytes: DEFAULT_LIMIT,
        }
    }
    fn fixture() -> tempfile::TempDir {
        let t = tempfile::tempdir().unwrap();
        fs::create_dir_all(t.path().join("src/nested/empty")).unwrap();
        fs::write(t.path().join("src/a.txt"), b"alpha bytes\n").unwrap();
        fs::write(t.path().join("src/nested/b.bin"), [0, 1, 2, 255]).unwrap();
        t
    }
    #[test]
    fn all_formats_roundtrip_folder_and_publish_refuses_existing() {
        for format in [
            ArchiveFormat::Zip,
            ArchiveFormat::Sevenz,
            ArchiveFormat::TarZst,
            ArchiveFormat::TarGz,
            ArchiveFormat::TarLz4,
        ] {
            let t = fixture();
            let source = t.path().join("src");
            let archive_path = t.path().join(format!("archive.{}", format.label()));
            let stage = t.path().join("stage");
            fs::create_dir(&stage).unwrap();
            let mut r = request(
                "create",
                vec![source.clone()],
                Some(archive_path.clone()),
                Some(format),
            );
            let created = execute(&r, &stage, |_| {}).unwrap();
            assert!(created.output_bytes > 0);
            assert_eq!(
                inspect_archive(&stage.join("artifact"), DEFAULT_LIMIT)
                    .unwrap()
                    .format,
                format.label()
            );
            publish(&r, &stage, &created).unwrap();
            let extract = t.path().join("extract-stage");
            fs::create_dir(&extract).unwrap();
            r = request(
                "extract",
                vec![archive_path],
                Some(t.path().join("out")),
                None,
            );
            let result = execute(&r, &extract, |_| {}).unwrap();
            assert_eq!(
                fs::read(extract.join("decoded/a.txt")).unwrap(),
                b"alpha bytes\n"
            );
            assert_eq!(
                fs::read(extract.join("decoded/nested/b.bin")).unwrap(),
                [0, 1, 2, 255]
            );
            let occupied = t.path().join("occupied");
            fs::create_dir(&occupied).unwrap();
            r.destination = Some(occupied);
            assert!(publish(&r, &extract, &result).is_err());
        }
    }
    #[test]
    fn selective_zip_extract_validates_selection() {
        let t = fixture();
        let stage = t.path().join("create-stage");
        fs::create_dir(&stage).unwrap();
        let archive_path = t.path().join("a.zip");
        let r = request(
            "create",
            vec![t.path().join("src")],
            Some(archive_path.clone()),
            Some(ArchiveFormat::Zip),
        );
        let created = execute(&r, &stage, |_| {}).unwrap();
        publish(&r, &stage, &created).unwrap();
        let decoded = t.path().join("decoded-stage");
        fs::create_dir(&decoded).unwrap();
        let mut x = request(
            "extract",
            vec![archive_path],
            Some(t.path().join("out")),
            None,
        );
        x.selected_entries = vec!["a.txt".into()];
        execute(&x, &decoded, |_| {}).unwrap();
        assert!(decoded.join("decoded/a.txt").exists());
        assert!(!decoded.join("decoded/nested/b.bin").exists());
        let bad = t.path().join("bad-stage");
        fs::create_dir(&bad).unwrap();
        x.selected_entries = vec!["../oops".into()];
        assert!(execute(&x, &bad, |_| {}).is_err());
    }
    #[test]
    fn inspection_is_magic_based_and_rejects_truncated_zip() {
        let t = fixture();
        let bad = t.path().join("fake.zip");
        fs::write(&bad, b"PK\x03\x04truncated").unwrap();
        assert!(inspect_archive(&bad, DEFAULT_LIMIT).is_err());
    }
    #[test]
    fn selected_directories_are_retained_and_multi_input_roundtrips() {
        let t = fixture();
        let stage = t.path().join("multi-stage");
        fs::create_dir(&stage).unwrap();
        let mut r = request(
            "create",
            vec![t.path().join("src/a.txt"), t.path().join("src/nested")],
            Some(t.path().join("multi.zip")),
            Some(ArchiveFormat::Zip),
        );
        let result = execute(&r, &stage, |_| {}).unwrap();
        assert!(inspect_archive(&stage.join("artifact"), DEFAULT_LIMIT)
            .unwrap()
            .entries
            .iter()
            .any(|e| e.name == "nested/empty"));
        publish(&r, &stage, &result).unwrap();
        let extract_stage = t.path().join("selected-stage");
        fs::create_dir(&extract_stage).unwrap();
        r = request(
            "extract",
            vec![t.path().join("multi.zip")],
            Some(t.path().join("out")),
            None,
        );
        r.selected_entries = vec!["nested".into()];
        execute(&r, &extract_stage, |_| {}).unwrap();
        assert!(extract_stage.join("decoded/nested/empty").is_dir());
        assert!(!extract_stage.join("decoded/a.txt").is_file());
    }
    #[test]
    fn rejects_multi_selected_basename_collisions_before_staging() {
        let t = tempfile::tempdir().unwrap();
        let a = t.path().join("a");
        let b = t.path().join("b");
        fs::create_dir(&a).unwrap();
        fs::create_dir(&b).unwrap();
        fs::write(a.join("same.txt"), b"a").unwrap();
        fs::write(b.join("same.txt"), b"b").unwrap();
        let stage = t.path().join("stage");
        fs::create_dir(&stage).unwrap();
        let r = request(
            "create",
            vec![a.join("same.txt"), b.join("same.txt")],
            Some(t.path().join("out.zip")),
            Some(ArchiveFormat::Zip),
        );
        assert!(execute(&r, &stage, |_| {}).is_err());
        assert!(!stage.join("sources").exists());
    }
    #[test]
    fn create_reports_real_bounded_phases_and_cli_fails_when_result_cannot_persist() {
        let t = fixture();
        let stage = t.path().join("phase-stage");
        fs::create_dir(&stage).unwrap();
        let r = request(
            "create",
            vec![t.path().join("src")],
            Some(t.path().join("out.zip")),
            Some(ArchiveFormat::Zip),
        );
        let phases = std::sync::Mutex::new(Vec::new());
        execute(&r, &stage, |p| phases.lock().unwrap().push(p.phase)).unwrap();
        assert_eq!(
            *phases.lock().unwrap(),
            ["preparing", "compressing", "complete"]
        );

        let request_path = t.path().join("request.json");
        let progress_path = t.path().join("progress.json");
        fs::write(
            &request_path,
            serde_json::to_vec(&CliRequest {
                request: r,
                staging: stage,
            })
            .unwrap(),
        )
        .unwrap();
        let args = vec![
            "--desktop-worker".into(),
            request_path.into_os_string(),
            t.path().join("missing/result.json").into_os_string(),
            progress_path.into_os_string(),
        ];
        assert_eq!(run_worker_cli(&args), Some(1));
    }
    #[test]
    fn publication_rejects_racing_existing_destination_without_modifying_it() {
        let t = fixture();
        let stage = t.path().join("stage");
        fs::create_dir(&stage).unwrap();
        fs::write(stage.join("artifact"), b"archive").unwrap();
        let dest = t.path().join("out.zip");
        fs::write(&dest, b"keep").unwrap();
        let r = request(
            "create",
            vec![t.path().join("src/a.txt")],
            Some(dest.clone()),
            Some(ArchiveFormat::Zip),
        );
        let result = WorkerResult {
            output_kind: "file".into(),
            input_bytes: 1,
            output_bytes: 7,
            message: String::new(),
        };
        assert!(publish(&r, &stage, &result).is_err());
        assert_eq!(fs::read(dest).unwrap(), b"keep");
    }
    #[test]
    fn create_rejects_destination_inside_source_and_worker_cli_runs_core() {
        let t = fixture();
        let source = t.path().join("src");
        let r = request(
            "create",
            vec![source.clone()],
            Some(source.join("bad.zip")),
            Some(ArchiveFormat::Zip),
        );
        let stage = t.path().join("reject-stage");
        fs::create_dir(&stage).unwrap();
        assert!(execute(&r, &stage, |_| {}).is_err());

        let stage = t.path().join("worker-stage");
        fs::create_dir(&stage).unwrap();
        let archive_path = t.path().join("worker.zip");
        let req = request(
            "create",
            vec![source],
            Some(archive_path.clone()),
            Some(ArchiveFormat::Zip),
        );
        let req_file = t.path().join("request.json");
        let result_file = t.path().join("result.json");
        let progress_file = t.path().join("progress.json");
        fs::write(
            &req_file,
            serde_json::to_vec(&CliRequest {
                request: req,
                staging: stage,
            })
            .unwrap(),
        )
        .unwrap();
        let args = vec![
            "--desktop-worker".into(),
            req_file.into_os_string(),
            result_file.clone().into_os_string(),
            progress_file.clone().into_os_string(),
        ];
        assert_eq!(run_worker_cli(&args), Some(0));
        let result: CliResult = serde_json::from_slice(&fs::read(result_file).unwrap()).unwrap();
        assert!(result.ok);
        assert_eq!(
            serde_json::from_slice::<Progress>(&fs::read(progress_file).unwrap())
                .unwrap()
                .phase,
            "complete"
        );
    }
}
