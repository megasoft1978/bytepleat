use bytepleat_desktop_core::{ArchiveFormat, OperationRequest};
use serde_json::json;
use std::{fs, process::Command};

#[test]
fn worker_binary_executes_a_generated_create_request() {
    let temp = tempfile::tempdir().unwrap();
    let input = temp.path().join("sample.txt");
    fs::write(&input, b"generated worker fixture").unwrap();
    let staging = temp.path().join("stage");
    fs::create_dir(&staging).unwrap();
    let request = OperationRequest {
        action: "create".into(),
        inputs: vec![input],
        destination: Some(temp.path().join("out.zip")),
        format: Some(ArchiveFormat::Zip),
        selected_entries: vec![],
        selective: false,
        max_output_bytes: 1024 * 1024,
    };
    let request_path = temp.path().join("request.json");
    let result_path = temp.path().join("result.json");
    let progress_path = temp.path().join("progress.json");
    fs::write(
        &request_path,
        serde_json::to_vec(&json!({"request":request,"staging":staging})).unwrap(),
    )
    .unwrap();
    let status = Command::new(env!("CARGO_BIN_EXE_bytepleat-worker"))
        .arg("--desktop-worker")
        .arg(request_path)
        .arg(&result_path)
        .arg(&progress_path)
        .status()
        .unwrap();
    assert!(status.success());
    let result: serde_json::Value =
        serde_json::from_slice(&fs::read(result_path).unwrap()).unwrap();
    assert_eq!(result["ok"], true);
    assert!(temp.path().join("stage/artifact").is_file());
    let progress: serde_json::Value =
        serde_json::from_slice(&fs::read(progress_path).unwrap()).unwrap();
    assert_eq!(progress["phase"], "complete");
}

#[test]
fn child_worker_inspects_generated_zip_and_tar_without_publishing() {
    for format in [ArchiveFormat::Zip, ArchiveFormat::TarZst] {
        let temp = tempfile::tempdir().unwrap();
        let input = temp.path().join("sample.txt");
        fs::write(&input, b"inspection fixture bytes").unwrap();
        let archive = temp.path().join(if format == ArchiveFormat::Zip {
            "sample.zip"
        } else {
            "sample.tar.zst"
        });
        let create_stage = temp.path().join("create-stage");
        fs::create_dir(&create_stage).unwrap();
        let create = OperationRequest {
            action: "create".into(),
            inputs: vec![input],
            destination: Some(archive.clone()),
            format: Some(format),
            selected_entries: vec![],
            selective: false,
            max_output_bytes: 1024 * 1024,
        };
        let created = bytepleat_desktop_core::execute(&create, &create_stage, |_| {}).unwrap();
        bytepleat_desktop_core::publish(&create, &create_stage, &created).unwrap();

        let staging = temp.path().join("inspect-stage");
        fs::create_dir(&staging).unwrap();
        let request = OperationRequest {
            action: "inspect".into(),
            inputs: vec![archive],
            destination: None,
            format: None,
            selected_entries: vec![],
            selective: false,
            max_output_bytes: 1024 * 1024,
        };
        let request_path = temp.path().join("inspect-request.json");
        let result_path = temp.path().join("inspect-result.json");
        let progress_path = temp.path().join("inspect-progress.json");
        fs::write(
            &request_path,
            serde_json::to_vec(&json!({"request":request,"staging":staging})).unwrap(),
        )
        .unwrap();
        let status = Command::new(env!("CARGO_BIN_EXE_bytepleat-worker"))
            .arg("--desktop-worker")
            .arg(&request_path)
            .arg(&result_path)
            .arg(&progress_path)
            .status()
            .unwrap();
        assert!(status.success());
        let result: serde_json::Value =
            serde_json::from_slice(&fs::read(result_path).unwrap()).unwrap();
        assert_eq!(result["ok"], true);
        assert_eq!(result["result"]["output_kind"], "none");
        assert_eq!(result["result"]["listing"]["total_entries"], 1);
        assert_eq!(
            result["result"]["listing"]["entries"][0]["name"],
            "sample.txt"
        );
        assert!(!staging.join("artifact").exists());
        if format == ArchiveFormat::TarZst {
            assert_eq!(
                fs::read(staging.join("inspection-decoded/sample.txt")).unwrap(),
                b"inspection fixture bytes"
            );
        }
        assert!(
            fs::read(temp.path().join("inspect-result.json"))
                .unwrap()
                .len()
                <= 1024 * 1024
        );
    }
}

#[test]
fn worker_rejects_missing_and_corrupt_requests_without_publishing() {
    let temp = tempfile::tempdir().unwrap();
    let staging = temp.path().join("stage");
    fs::create_dir(&staging).unwrap();
    let result = temp.path().join("result.json");
    let progress = temp.path().join("progress.json");
    let binary = env!("CARGO_BIN_EXE_bytepleat-worker");

    let missing_status = Command::new(binary)
        .arg("--desktop-worker")
        .arg(temp.path().join("missing.json"))
        .arg(&result)
        .arg(&progress)
        .status()
        .unwrap();
    assert!(!missing_status.success());
    assert!(fs::read(&result).unwrap().len() < 1024 * 1024);
    assert!(!staging.join("artifact").exists());

    let corrupt = temp.path().join("corrupt.json");
    fs::write(&corrupt, b"{").unwrap();
    let corrupt_status = Command::new(binary)
        .arg("--desktop-worker")
        .arg(corrupt)
        .arg(&result)
        .arg(&progress)
        .status()
        .unwrap();
    assert!(!corrupt_status.success());
    let answer: serde_json::Value = serde_json::from_slice(&fs::read(result).unwrap()).unwrap();
    assert_eq!(answer["ok"], false);
    assert!(!staging.join("artifact").exists());
}
