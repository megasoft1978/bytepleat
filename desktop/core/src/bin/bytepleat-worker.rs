use std::{ffi::OsString, process};
fn main() {
    let args: Vec<OsString> = std::env::args_os().skip(1).collect();
    match bytepleat_desktop_core::run_worker_cli(&args) {
        Some(code) => process::exit(code),
        None => {
            eprintln!(
                "usage: bytepleat-worker --desktop-worker REQUEST_JSON RESULT_JSON PROGRESS_JSON"
            );
            process::exit(2)
        }
    }
}
