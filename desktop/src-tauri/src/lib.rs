use bytepleat_desktop_core::{publish, ArchiveListing, OperationRequest, Progress, WorkerResult};
use serde::{Deserialize, Serialize};
use std::{
    ffi::OsString,
    fs,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};
use tauri::{Emitter, Manager, State};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;
use tempfile::TempDir;

const MAX_JSON: u64 = 1024 * 1024;
const HISTORY_LIMIT: usize = 40;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct JobSnapshot {
    pub id: String,
    pub action: String,
    pub phase: String,
    pub state: String,
    pub processed_bytes: u64,
    pub total_bytes: Option<u64>,
    pub message: String,
    pub output: Option<String>,
    pub error: Option<String>,
}

#[derive(Clone, Default, Serialize)]
struct Selection {
    action: String,
    paths: Vec<String>,
    error: Option<String>,
}

#[derive(Default)]
struct Broker {
    jobs: Mutex<Vec<JobSnapshot>>,
    child: Mutex<Option<Child>>,
    active_id: Mutex<Option<String>>,
    cancel: Mutex<bool>,
    shutting_down: Mutex<bool>,
    selection: Mutex<Selection>,
}

pub fn run_worker_cli(args: &[OsString]) -> Option<i32> {
    if args.first().map(|s| s == "--desktop-worker") != Some(true) {
        return None;
    }
    Some(bytepleat_desktop_core::run_worker_cli(args).unwrap_or(2))
}

fn path_strings(paths: impl IntoIterator<Item = PathBuf>) -> Result<Vec<String>, String> {
    paths
        .into_iter()
        .map(|p| {
            p.into_os_string().into_string().map_err(|_| {
                "A selected path cannot be represented as UTF-8 by the desktop interface"
                    .to_string()
            })
        })
        .collect()
}

fn argument_selection(args: &[OsString]) -> Selection {
    let mut it = args.iter();
    if it.next().and_then(|v| v.to_str()).is_some_and(|v| {
        Path::new(v)
            .file_name()
            .and_then(|n| n.to_str())
            .is_some_and(|n| n.starts_with("bytepleat-desktop"))
    }) {
        // The single-instance plugin forwards argv including argv[0].
    } else {
        it = args.iter();
    }
    let action = match it.next().and_then(|v| v.to_str()) {
        Some("--create") => "create",
        Some("--extract") => "extract",
        Some("--open") => "open",
        _ => {
            let values: Vec<_> = if args.first().and_then(|v| v.to_str()).is_some_and(|v| {
                Path::new(v)
                    .file_name()
                    .and_then(|n| n.to_str())
                    .is_some_and(|n| n.starts_with("bytepleat-desktop"))
            }) {
                args.iter().skip(1).collect()
            } else {
                args.iter().collect()
            };
            if values
                .iter()
                .any(|v| v.to_str().is_some_and(|v| v.starts_with('-')))
            {
                return Selection {
                    action: "open".into(),
                    paths: vec![],
                    error: Some("Unsupported command-line option".into()),
                };
            }
            return match path_strings(values.into_iter().map(PathBuf::from)) {
                Ok(paths) => Selection {
                    action: "open".into(),
                    paths,
                    error: None,
                },
                Err(error) => Selection {
                    action: "open".into(),
                    paths: vec![],
                    error: Some(error),
                },
            };
        }
    };
    if it.next().map(|v| v == "--") != Some(true) {
        return Selection {
            action: action.into(),
            paths: vec![],
            error: Some("Expected -- before selected paths".into()),
        };
    }
    match path_strings(it.map(PathBuf::from)) {
        Ok(paths) => Selection {
            action: action.into(),
            paths,
            error: None,
        },
        Err(error) => Selection {
            action: action.into(),
            paths: vec![],
            error: Some(error),
        },
    }
}

fn remember_selection(state: &Broker, selection: Selection) {
    if let Ok(mut current) = state.selection.lock() {
        *current = selection;
    }
}

#[tauri::command]
async fn choose_inputs(app: tauri::AppHandle) -> Result<Vec<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let selected = app
            .dialog()
            .file()
            .set_title("Choose files or folders")
            .blocking_pick_files()
            .unwrap_or_default();
        let paths = selected
            .into_iter()
            .map(|p| {
                p.into_path()
                    .map_err(|_| "A selected item is not a local filesystem path".to_string())
            })
            .collect::<Result<Vec<_>, _>>()?;
        path_strings(paths)
    })
    .await
    .map_err(|e| format!("File selection task failed: {e}"))?
}

#[tauri::command]
async fn choose_input_directory(app: tauri::AppHandle) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let selected = app
            .dialog()
            .file()
            .set_title("Choose a folder to archive")
            .blocking_pick_folder()
            .map(|p| {
                p.into_path()
                    .map_err(|_| "The selected folder is not a local filesystem path".to_string())
            })
            .transpose()?;
        selected
            .map(|path| path_strings([path]).map(|mut paths| paths.remove(0)))
            .transpose()
    })
    .await
    .map_err(|e| format!("Folder selection task failed: {e}"))?
}

#[tauri::command]
async fn choose_directory(app: tauri::AppHandle) -> Result<Option<String>, String> {
    tauri::async_runtime::spawn_blocking(move || {
        let selected = app
            .dialog()
            .file()
            .set_title("Choose destination folder")
            .blocking_pick_folder()
            .map(|p| {
                p.into_path()
                    .map_err(|_| "The selected folder is not a local filesystem path".to_string())
            })
            .transpose()?;
        selected
            .map(|path| path_strings([path]).map(|mut paths| paths.remove(0)))
            .transpose()
    })
    .await
    .map_err(|e| format!("Destination selection task failed: {e}"))?
}

#[tauri::command]
async fn choose_output(app: tauri::AppHandle, format: String) -> Result<Option<String>, String> {
    let extension = match format.as_str() {
        "zip" => "zip",
        "7z" => "7z",
        "tar.zst" => "tar.zst",
        "tar.gz" => "tar.gz",
        "tar.lz4" => "tar.lz4",
        _ => return Err("Unsupported archive format".into()),
    };
    let file_name = format!("Archive.{extension}");
    tauri::async_runtime::spawn_blocking(move || {
        let selected = app
            .dialog()
            .file()
            .set_title("Save archive")
            .set_file_name(file_name)
            .blocking_save_file()
            .map(|p| {
                p.into_path()
                    .map_err(|_| "The selected output is not a local filesystem path".to_string())
            })
            .transpose()?;
        selected
            .map(|path| path_strings([path]).map(|mut paths| paths.remove(0)))
            .transpose()
    })
    .await
    .map_err(|e| format!("Output selection task failed: {e}"))?
}

#[tauri::command]
fn initial_selection(state: State<'_, Arc<Broker>>) -> Selection {
    state
        .selection
        .lock()
        .map(|v| v.clone())
        .unwrap_or(Selection {
            action: "open".into(),
            paths: vec![],
            error: None,
        })
}

#[tauri::command]
fn jobs(state: State<'_, Arc<Broker>>) -> Vec<JobSnapshot> {
    state.jobs.lock().map(|v| v.clone()).unwrap_or_default()
}

#[tauri::command]
async fn inspect_archive(path: String) -> Result<ArchiveListing, String> {
    let path = PathBuf::from(path);
    tauri::async_runtime::spawn_blocking(move || {
        bytepleat_desktop_core::inspect_archive(&path, 1024 * 1024 * 1024)
    })
    .await
    .map_err(|e| format!("Archive inspection task failed: {e}"))?
}

#[tauri::command]
fn start_job(
    app: tauri::AppHandle,
    state: State<'_, Arc<Broker>>,
    request: OperationRequest,
) -> Result<String, String> {
    if state.shutting_down.lock().map(|v| *v).unwrap_or(true) {
        return Err("The application is shutting down".into());
    }
    validate_request(&request)?;
    let mut jobs = state
        .jobs
        .lock()
        .map_err(|_| "Job state unavailable".to_string())?;
    if state
        .active_id
        .lock()
        .map_err(|_| "Job state unavailable".to_string())?
        .is_some()
    {
        return Err(
            "A job is already running. Wait for it to finish before starting another.".into(),
        );
    }
    let id = unique_id();
    jobs.insert(
        0,
        JobSnapshot {
            id: id.clone(),
            action: request.action.clone(),
            phase: "preparing".into(),
            state: "queued".into(),
            processed_bytes: 0,
            total_bytes: None,
            message: "Preparing private staging area".into(),
            output: None,
            error: None,
        },
    );
    jobs.truncate(HISTORY_LIMIT);
    *state
        .active_id
        .lock()
        .map_err(|_| "Job state unavailable".to_string())? = Some(id.clone());
    *state
        .cancel
        .lock()
        .map_err(|_| "Job state unavailable".to_string())? = false;
    drop(jobs);

    let broker = Arc::clone(&state);
    let worker_id = id.clone();
    thread::spawn(move || run_job(app, broker, worker_id, request));
    Ok(id)
}

#[tauri::command]
fn cancel_job(state: State<'_, Arc<Broker>>, id: String) -> bool {
    let broker = state.inner();
    if !mark_cancelling(broker, &id) {
        return false;
    }
    if let Ok(mut child) = broker.child.lock() {
        if let Some(child) = child.as_mut() {
            let _ = child.kill();
        }
    }
    true
}

fn mark_cancelling(broker: &Broker, id: &str) -> bool {
    if broker
        .active_id
        .lock()
        .ok()
        .and_then(|v| v.clone())
        .as_deref()
        != Some(id)
    {
        return false;
    }
    let Ok(mut jobs) = broker.jobs.lock() else {
        return false;
    };
    let Some(job) = jobs
        .iter_mut()
        .find(|j| j.id == id && matches!(j.state.as_str(), "queued" | "running"))
    else {
        return false;
    };
    let Ok(mut cancel) = broker.cancel.lock() else {
        return false;
    };
    *cancel = true;
    job.state = "cancelling".into();
    job.message = "Stopping and reaping the worker".into();
    true
}

fn publish_under_job_lock(
    broker: &Broker,
    id: &str,
    action: impl FnOnce() -> Result<Option<String>, String>,
) -> Result<Option<String>, String> {
    let mut jobs = broker
        .jobs
        .lock()
        .map_err(|_| "Job state unavailable".to_string())?;
    if !jobs.iter().any(|job| job.id == id) {
        return Err("Job no longer exists".into());
    }
    let cancelled = broker
        .cancel
        .lock()
        .map_err(|_| "Job state unavailable".to_string())?;
    if *cancelled {
        return Err("Job was cancelled before publication".into());
    }
    let output = match action() {
        Ok(output) => output,
        Err(error) => {
            if let Some(job) = jobs.iter_mut().find(|job| job.id == id) {
                job.state = "failed".into();
                job.phase = "Publication failed".into();
                job.message = error.clone();
                job.error = Some(error.clone());
            }
            return Err(error);
        }
    };
    if let Some(job) = jobs.iter_mut().find(|job| job.id == id) {
        job.state = "completed".into();
        job.phase = "Complete".into();
        job.message = "Archive published successfully".into();
        job.output = output.clone();
    }
    Ok(output)
}

#[tauri::command]
fn open_destination(
    app: tauri::AppHandle,
    state: State<'_, Arc<Broker>>,
    id: String,
) -> Result<(), String> {
    let output = state
        .jobs
        .lock()
        .map_err(|_| "Job state unavailable".to_string())?
        .iter()
        .find(|j| j.id == id && j.state == "completed")
        .and_then(|j| j.output.clone())
        .ok_or_else(|| "This job has no completed destination".to_string())?;
    let path = PathBuf::from(output);
    let folder = if path.is_dir() {
        path
    } else {
        path.parent().unwrap_or(Path::new(".")).to_path_buf()
    };
    app.opener()
        .open_path(folder.to_string_lossy().into_owned(), None::<&str>)
        .map_err(|e| e.to_string())
}

fn validate_request(request: &OperationRequest) -> Result<(), String> {
    if !matches!(request.action.as_str(), "create" | "extract" | "test") {
        return Err("Unsupported operation".into());
    }
    if request.inputs.is_empty() {
        return Err("Choose at least one input".into());
    }
    if request.max_output_bytes == 0 || request.max_output_bytes > 1024 * 1024 * 1024 {
        return Err("Output limit must be between 1 byte and 1 GiB".into());
    }
    for path in &request.inputs {
        let meta = fs::symlink_metadata(path)
            .map_err(|e| format!("Cannot access {}: {e}", path.display()))?;
        if meta.file_type().is_symlink() {
            return Err(format!(
                "Symbolic links are not accepted as inputs: {}",
                path.display()
            ));
        }
    }
    if request.action == "create" && request.format.is_none() {
        return Err("Choose an archive format".into());
    }
    Ok(())
}

fn unique_id() -> String {
    format!(
        "{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    )
}

#[derive(Serialize)]
struct WorkerRequest<'a> {
    request: &'a OperationRequest,
    staging: &'a Path,
}

fn run_job(app: tauri::AppHandle, broker: Arc<Broker>, id: String, request: OperationRequest) {
    let _cleanup = JobCleanup {
        broker: Arc::clone(&broker),
        id: id.clone(),
    };
    let staging_parent = request
        .destination
        .as_deref()
        .and_then(Path::parent)
        .filter(|p| p.is_dir());
    let temp = match staging_parent
        .map(TempDir::new_in)
        .unwrap_or_else(TempDir::new)
    {
        Ok(v) => v,
        Err(e) => {
            fail_before_worker(&broker, &id, "Unable to prepare staging", e.to_string());
            return;
        }
    };
    let temp = Arc::new(temp);
    let stage = temp.path().to_path_buf();
    let request_path = stage.join("request.json");
    let result_path = stage.join("result.json");
    let progress_path = stage.join("progress.json");
    let payload = match serde_json::to_vec(&WorkerRequest {
        request: &request,
        staging: &stage,
    }) {
        Ok(v) if v.len() as u64 <= MAX_JSON => v,
        _ => {
            fail_before_worker(
                &broker,
                &id,
                "Could not encode worker request",
                "Worker request exceeded its bound".into(),
            );
            return;
        }
    };
    if let Err(e) = fs::write(&request_path, payload) {
        fail_before_worker(
            &broker,
            &id,
            "Unable to write worker request",
            e.to_string(),
        );
        return;
    }
    let executable = match std::env::current_exe() {
        Ok(v) => v,
        Err(e) => {
            fail_before_worker(
                &broker,
                &id,
                "Unable to locate worker executable",
                e.to_string(),
            );
            return;
        }
    };
    let child = match Command::new(executable)
        .arg("--desktop-worker")
        .arg(&request_path)
        .arg(&result_path)
        .arg(&progress_path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(v) => v,
        Err(e) => {
            fail_before_worker(&broker, &id, "Unable to start worker", e.to_string());
            return;
        }
    };
    *broker
        .child
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(child);
    set_job(
        &broker,
        &id,
        "running",
        "starting",
        "Worker started",
        0,
        None,
    );
    loop {
        let cancelled = broker.cancel.lock().map(|v| *v).unwrap_or(true);
        let status = {
            let mut slot = match broker.child.lock() {
                Ok(v) => v,
                Err(_) => break,
            };
            let Some(process) = slot.as_mut() else { break };
            if cancelled {
                let _ = process.kill();
            }
            process.try_wait().unwrap_or_default()
        };
        if let Ok(metadata) = fs::metadata(&progress_path) {
            if metadata.len() <= MAX_JSON {
                let Ok(data) = fs::read(&progress_path) else {
                    thread::sleep(Duration::from_millis(100));
                    continue;
                };
                if let Ok(progress) = serde_json::from_slice::<Progress>(&data) {
                    set_job(
                        &broker,
                        &id,
                        "running",
                        &progress.phase,
                        &progress.message,
                        progress.processed_bytes,
                        progress.total_bytes,
                    );
                }
            }
        }
        if let Some(status) = status {
            let cancelled = broker.cancel.lock().map(|v| *v).unwrap_or(false);
            if cancelled {
                finish(&broker, &id, "cancelled", "Cancelled", None, None);
            } else if status.success() {
                match read_worker_result(&result_path) {
                    Ok(result) if result.ok => match result.result {
                        Some(value) => {
                            let publish_result = publish_under_job_lock(&broker, &id, || {
                                publish(&request, &stage, &value)
                                    .map(|p| p.map(|p| p.to_string_lossy().into_owned()))
                            });
                            match publish_result {
                                Ok(output) => finish(
                                    &broker,
                                    &id,
                                    "completed",
                                    "Complete",
                                    Some(value.message),
                                    output,
                                ),
                                Err(error) => {
                                    finish_publication_error(&broker, &id, error);
                                }
                            }
                        }
                        None => finish(
                            &broker,
                            &id,
                            "failed",
                            "Worker returned no result",
                            Some("Invalid worker result".into()),
                            None,
                        ),
                    },
                    Ok(result) => finish(
                        &broker,
                        &id,
                        "failed",
                        "Operation failed",
                        result.error,
                        None,
                    ),
                    Err(error) => finish(
                        &broker,
                        &id,
                        "failed",
                        "Worker result unavailable",
                        Some(error),
                        None,
                    ),
                }
            } else {
                finish(
                    &broker,
                    &id,
                    "failed",
                    "Worker stopped unexpectedly",
                    Some(format!("Worker exited with {status}")),
                    None,
                );
            }
            break;
        }
        thread::sleep(Duration::from_millis(100));
    }
    if let Ok(mut slot) = broker.child.lock() {
        if let Some(mut process) = slot.take() {
            let _ = process.wait();
        }
    }
    let _ = app.emit("jobs-changed", ());
    drop(temp);
}

struct JobCleanup {
    broker: Arc<Broker>,
    id: String,
}
impl Drop for JobCleanup {
    fn drop(&mut self) {
        let mut slot = self
            .broker
            .child
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        if let Some(mut child) = slot.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        release_job_slot(&self.broker, &self.id);
    }
}

fn fail_before_worker(broker: &Broker, id: &str, phase: &str, error: String) {
    finish(broker, id, "failed", phase, Some(error), None);
}

fn finish_publication_error(broker: &Broker, id: &str, error: String) {
    if broker.cancel.lock().map(|v| *v).unwrap_or(false) {
        finish(broker, id, "cancelled", "Cancelled", None, None);
    } else {
        finish(
            broker,
            id,
            "failed",
            "Publication failed",
            Some(error),
            None,
        );
    }
}

fn release_job_slot(broker: &Broker, id: &str) {
    let mut active = broker
        .active_id
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner);
    if active.as_deref() == Some(id) {
        *active = None;
    }
    *broker
        .cancel
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner) = false;
}

#[derive(Deserialize)]
struct WorkerResponse {
    ok: bool,
    result: Option<WorkerResult>,
    error: Option<String>,
}
fn read_worker_result(path: &Path) -> Result<WorkerResponse, String> {
    let metadata = fs::metadata(path).map_err(|e| e.to_string())?;
    if metadata.len() > MAX_JSON {
        return Err("Worker result exceeded size limit".into());
    }
    serde_json::from_slice(&fs::read(path).map_err(|e| e.to_string())?).map_err(|e| e.to_string())
}
fn set_job(
    broker: &Broker,
    id: &str,
    state: &str,
    phase: &str,
    message: &str,
    done: u64,
    total: Option<u64>,
) {
    if let Ok(mut jobs) = broker.jobs.lock() {
        if let Some(job) = jobs.iter_mut().find(|j| j.id == id) {
            if job.state == "cancelling" {
                return;
            }
            job.state = state.into();
            job.phase = phase.into();
            job.message = message.into();
            job.processed_bytes = done;
            job.total_bytes = total;
        }
    }
}
fn finish(
    broker: &Broker,
    id: &str,
    state: &str,
    phase: &str,
    error: Option<String>,
    output: Option<String>,
) {
    if let Ok(mut jobs) = broker.jobs.lock() {
        if let Some(job) = jobs.iter_mut().find(|j| j.id == id) {
            job.state = state.into();
            job.phase = phase.into();
            job.message = error.clone().unwrap_or_else(|| phase.into());
            if state == "failed" {
                job.error = error;
            } else {
                job.message = error.unwrap_or_else(|| phase.into());
            }
            job.output = output;
        }
    }
}

pub fn run() {
    let startup = argument_selection(&std::env::args_os().skip(1).collect::<Vec<_>>());
    let broker = Arc::new(Broker {
        selection: Mutex::new(startup),
        ..Broker::default()
    });
    let single_instance_broker = Arc::clone(&broker);
    tauri::Builder::default()
        .plugin(
            tauri_plugin_single_instance::Builder::new()
                .callback(move |app, args, _cwd| {
                    let parsed = argument_selection(
                        &args.into_iter().map(OsString::from).collect::<Vec<_>>(),
                    );
                    remember_selection(&single_instance_broker, parsed.clone());
                    let _ = app.emit("selection", parsed);
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.unminimize();
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                })
                .build(),
        )
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(broker)
        .invoke_handler(tauri::generate_handler![
            choose_inputs,
            choose_input_directory,
            choose_directory,
            choose_output,
            initial_selection,
            start_job,
            jobs,
            cancel_job,
            inspect_archive,
            open_destination
        ])
        .build(tauri::generate_context!())
        .expect("failed to build Bytepleat")
        .run(|app, event| match event {
            #[cfg(target_os = "macos")]
            tauri::RunEvent::Opened { urls } => {
                let paths = urls
                    .into_iter()
                    .filter_map(|u| u.to_file_path().ok())
                    .collect::<Vec<_>>();
                let selection = match path_strings(paths) {
                    Ok(paths) => Selection {
                        action: "open".into(),
                        paths,
                        error: None,
                    },
                    Err(error) => Selection {
                        action: "open".into(),
                        paths: vec![],
                        error: Some(error),
                    },
                };
                if let Some(state) = app.try_state::<Arc<Broker>>() {
                    remember_selection(&state, selection.clone());
                    let _ = app.emit("selection", selection);
                }
            }
            tauri::RunEvent::ExitRequested { api, .. } => {
                if let Some(state) = app.try_state::<Arc<Broker>>() {
                    let active = state.active_id.lock().ok().and_then(|v| v.clone());
                    if let Some(id) = active {
                        api.prevent_exit();
                        if let Ok(mut shutting_down) = state.shutting_down.lock() {
                            *shutting_down = true;
                        }
                        let _ = mark_cancelling(&state, &id);
                        if let Ok(mut child) = state.child.lock() {
                            if let Some(child) = child.as_mut() {
                                let _ = child.kill();
                            }
                        }
                        let app = app.clone();
                        let state = Arc::clone(&state);
                        thread::spawn(move || {
                            loop {
                                if state.active_id.lock().map(|v| v.is_none()).unwrap_or(true) {
                                    break;
                                }
                                thread::sleep(Duration::from_millis(25));
                            }
                            app.exit(0);
                        });
                    }
                }
            }
            _ => {}
        });
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;

    fn running_broker() -> Arc<Broker> {
        Arc::new(Broker {
            jobs: Mutex::new(vec![JobSnapshot {
                id: "job-1".into(),
                action: "create".into(),
                phase: "running".into(),
                state: "running".into(),
                processed_bytes: 0,
                total_bytes: None,
                message: "running".into(),
                output: None,
                error: None,
            }]),
            active_id: Mutex::new(Some("job-1".into())),
            ..Broker::default()
        })
    }

    #[test]
    fn invocation_preserves_path_order_with_or_without_argv_zero() {
        let direct = vec![
            OsString::from("--create"),
            OsString::from("--"),
            OsString::from("/tmp/first file"),
            OsString::from("/tmp/second"),
        ];
        let forwarded = vec![
            OsString::from("/Applications/Bytepleat.app/Contents/MacOS/bytepleat-desktop"),
            OsString::from("--create"),
            OsString::from("--"),
            OsString::from("/tmp/first file"),
            OsString::from("/tmp/second"),
        ];
        for args in [direct, forwarded] {
            let selected = argument_selection(&args);
            assert_eq!(selected.action, "create");
            assert_eq!(selected.paths, ["/tmp/first file", "/tmp/second"]);
        }
    }

    #[test]
    fn cancellation_before_publication_skips_publish() {
        let broker = running_broker();
        assert!(mark_cancelling(&broker, "job-1"));
        let called = std::sync::atomic::AtomicBool::new(false);
        let result = publish_under_job_lock(&broker, "job-1", || {
            called.store(true, std::sync::atomic::Ordering::SeqCst);
            Ok(None)
        });
        assert!(result.is_err());
        assert!(!called.load(std::sync::atomic::Ordering::SeqCst));
    }

    #[test]
    fn cancellation_winning_publication_error_is_reported_as_cancelled() {
        let broker = running_broker();
        assert!(mark_cancelling(&broker, "job-1"));
        finish_publication_error(&broker, "job-1", "publication refused".into());
        assert_eq!(broker.jobs.lock().unwrap()[0].state, "cancelled");
        assert!(broker.jobs.lock().unwrap()[0].error.is_none());
    }

    #[test]
    fn cleanup_releases_failed_job_slot_for_next_job() {
        let broker = running_broker();
        let temp = TempDir::new().unwrap();
        let stage_path = temp.path().to_path_buf();
        let child = Command::new("sleep").arg("30").spawn().unwrap();
        let child_pid = child.id();
        *broker.child.lock().unwrap() = Some(child);
        let cleanup = JobCleanup {
            broker: Arc::clone(&broker),
            id: "job-1".into(),
        };
        drop(temp);
        drop(cleanup);
        assert!(!stage_path.exists(), "private staging must be removed");
        assert!(
            Command::new("kill")
                .arg("-0")
                .arg(child_pid.to_string())
                .stderr(Stdio::null())
                .status()
                .is_ok_and(|status| !status.success()),
            "owned worker must be reaped"
        );
        assert!(broker.active_id.lock().unwrap().is_none());
        *broker.active_id.lock().unwrap() = Some("job-2".into());
        assert_eq!(broker.active_id.lock().unwrap().as_deref(), Some("job-2"));
    }

    #[cfg(unix)]
    #[test]
    fn non_utf8_selection_is_rejected_instead_of_partially_forwarded() {
        use std::os::unix::ffi::OsStringExt;
        let paths = vec![
            PathBuf::from("/tmp/valid"),
            PathBuf::from(OsString::from_vec(vec![b'/', 0xff])),
        ];
        assert!(path_strings(paths).is_err());
    }

    #[test]
    fn publication_and_cancellation_are_serialized() {
        let broker = running_broker();
        let (entered_tx, entered_rx) = mpsc::channel();
        let (release_tx, release_rx) = mpsc::channel();
        let (cancel_tx, cancel_rx) = mpsc::channel();
        let publish_broker = Arc::clone(&broker);
        let publisher = thread::spawn(move || {
            publish_under_job_lock(&publish_broker, "job-1", || {
                entered_tx.send(()).unwrap();
                release_rx.recv().unwrap();
                Ok(Some("/destination/archive.zip".into()))
            })
        });
        entered_rx.recv().unwrap();
        let cancel_broker = Arc::clone(&broker);
        let canceller = thread::spawn(move || {
            cancel_tx
                .send(mark_cancelling(&cancel_broker, "job-1"))
                .unwrap()
        });
        assert!(
            cancel_rx.try_recv().is_err(),
            "cancel must wait while publication owns the job lock"
        );
        release_tx.send(()).unwrap();
        assert_eq!(
            publisher.join().unwrap().unwrap().as_deref(),
            Some("/destination/archive.zip")
        );
        canceller.join().unwrap();
        assert!(
            !cancel_rx.recv().unwrap(),
            "a completed publication cannot be cancelled afterward"
        );
        let jobs = broker.jobs.lock().unwrap();
        assert_eq!(jobs[0].state, "completed");
        assert_eq!(jobs[0].output.as_deref(), Some("/destination/archive.zip"));
    }
}
