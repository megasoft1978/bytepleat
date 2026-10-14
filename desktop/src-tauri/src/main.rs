#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    let args: Vec<std::ffi::OsString> = std::env::args_os().skip(1).collect();
    if let Some(code) = bytepleat_desktop_lib::run_worker_cli(&args) {
        std::process::exit(code);
    }
    bytepleat_desktop_lib::run();
}
