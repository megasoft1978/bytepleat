#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    let args: Vec<std::ffi::OsString> = std::env::args_os().skip(1).collect();
    if let Some(code) = bytepleat_desktop_lib::run_worker_cli(&args) {
        std::process::exit(code);
    }
    #[cfg(target_os = "linux")]
    if should_forward_startup(&args, std::env::var_os(REEXEC_GUARD_ENV).is_some()) {
        let invalid_args = args.iter().any(|arg| arg.to_str().is_none());
        let startup_id = std::env::var("DESKTOP_STARTUP_ID")
            .ok()
            .filter(|value| valid_startup_id(value));
        if invalid_args || startup_id.is_some() {
            let mut command =
                std::process::Command::new(std::env::current_exe().expect("current executable"));
            if invalid_args {
                command.arg(INVALID_SELECTION_PREFIX);
            } else if let Some(startup_id) = startup_id {
                command.arg(format!("{STARTUP_PREFIX}{startup_id}"));
            }
            command.env(REEXEC_GUARD_ENV, "1");
            command.args(["--open", "--"]);
            if !invalid_args {
                command.args(args);
            }
            use std::os::unix::process::CommandExt as _;
            let error = command.exec();
            if invalid_args {
                eprintln!("Bytepleat could not safely forward a non-UTF-8 selection: {error}");
                std::process::exit(2);
            }
            eprintln!("Bytepleat could not forward desktop launch context: {error}");
        }
    }
    bytepleat_desktop_lib::run();
}

#[cfg(target_os = "linux")]
const STARTUP_PREFIX: &str = "--bytepleat-internal-startup-v1=";
#[cfg(target_os = "linux")]
const INVALID_SELECTION_PREFIX: &str = "--bytepleat-internal-invalid-selection-v1";
#[cfg(target_os = "linux")]
const REEXEC_GUARD_ENV: &str = "BYTEPLEAT_INTERNAL_REEXEC_V1";

#[cfg(target_os = "linux")]
fn has_internal_metadata(args: &[std::ffi::OsString]) -> bool {
    let offset = usize::from(args.first().and_then(|v| v.to_str()).is_some_and(|v| {
        !v.starts_with('-')
            && std::path::Path::new(v)
                .file_name()
                .and_then(|n| n.to_str())
                .is_some_and(|n| n.starts_with("bytepleat-desktop"))
    }));
    args.get(offset)
        .and_then(|v| v.to_str())
        .is_some_and(|marker| {
            (marker == INVALID_SELECTION_PREFIX || marker.starts_with(STARTUP_PREFIX))
                && args.get(offset + 1).and_then(|v| v.to_str()) == Some("--open")
                && args.get(offset + 2).and_then(|v| v.to_str()) == Some("--")
        })
}

#[cfg(target_os = "linux")]
fn should_forward_startup(args: &[std::ffi::OsString], already_forwarded: bool) -> bool {
    !already_forwarded && !has_internal_metadata(args)
}

#[cfg(target_os = "linux")]
fn valid_startup_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 4096
        && !value
            .bytes()
            .any(|byte| byte == 0 || byte.is_ascii_control())
}

#[cfg(all(test, target_os = "linux"))]
mod linux_startup_tests {
    use super::*;
    use std::ffi::OsString;

    #[test]
    fn startup_id_bounds_and_loop_guard() {
        assert!(valid_startup_id("token with spaces"));
        assert!(!valid_startup_id(&"x".repeat(4097)));
        assert!(!valid_startup_id("bad\nvalue"));
        assert!(has_internal_metadata(&[
            OsString::from(format!("{STARTUP_PREFIX}id")),
            "--open".into(),
            "--".into()
        ]));
        assert!(!should_forward_startup(
            &[
                OsString::from(format!("{STARTUP_PREFIX}id")),
                "--open".into(),
                "--".into()
            ],
            false
        ));
        assert!(!should_forward_startup(
            &["--open".into(), "--".into(), "/tmp/archive.zip".into()],
            true
        ));
        assert!(!has_internal_metadata(&[OsString::from(format!(
            "{STARTUP_PREFIX}ordinary-file"
        ))]));
        assert!(has_internal_metadata(&[
            "/usr/bin/bytepleat-desktop".into(),
            INVALID_SELECTION_PREFIX.into(),
            "--open".into(),
            "--".into()
        ]));
    }

    #[test]
    fn slashed_startup_id_marker_is_not_argv_zero() {
        let marker = format!("{STARTUP_PREFIX}org.gnome.Nautilus-1-bytepleat-desktop-\"/usr/bin/bytepleat-desktop\"-0_TIME1");
        assert!(has_internal_metadata(&[
            OsString::from(marker),
            "--open".into(),
            "--".into()
        ]));
    }
}
