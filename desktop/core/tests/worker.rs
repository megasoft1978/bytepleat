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
