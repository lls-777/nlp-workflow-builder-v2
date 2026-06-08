from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from backend.python_service.main import create_app
from config import EXAMPLES_DIR
from core.orchestrator import Orchestrator
from storage.file_store import FileStore
from storage.sqlite_store import SQLiteStore


def create_test_client(tmp_path: Path) -> TestClient:
    uploads_dir = tmp_path / "uploads"
    orchestrator = Orchestrator(
        store=SQLiteStore(tmp_path / "app.db"),
        file_store=FileStore(
            uploads_dir=uploads_dir,
            artifacts_dir=tmp_path / "artifacts",
            allowed_source_roots=(EXAMPLES_DIR, uploads_dir),
        ),
    )
    return TestClient(create_app(orchestrator))


def create_session(client: TestClient) -> str:
    response = client.post("/api/sessions")
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "COLLECTING_REQUIREMENTS"
    return str(payload["session_id"])


def upload_file(
    client: TestClient,
    session_id: str,
    *,
    filename: str,
    content: bytes,
) -> List[Dict[str, str]]:
    response = client.post(
        f"/api/sessions/{session_id}/uploads",
        files=[("files", (filename, content, "application/octet-stream"))],
    )
    assert response.status_code == 200
    files = response.json()["files"]
    assert files[0]["name"] == filename
    assert "/" not in files[0]["id"]
    return files


def assert_no_absolute_paths(value: Any) -> None:
    serialized = json.dumps(value, ensure_ascii=False)
    assert "/Users/" not in serialized
    assert "source_path" not in serialized
    assert '"path"' not in serialized


def test_api_summary_prepare_execute_and_get_run(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)
    session_id = create_session(client)
    files = upload_file(
        client,
        session_id,
        filename="sample.txt",
        content=(EXAMPLES_DIR / "sample.txt").read_bytes(),
    )

    prepare = client.post(
        f"/api/sessions/{session_id}/prepare",
        json={"user_request": "请总结这份文件", "files": files},
    )
    assert prepare.status_code == 200
    prepare_payload = prepare.json()
    assert prepare_payload["state"] == "AWAITING_CONFIRMATION"
    assert prepare_payload["plan_text"]

    execute = client.post(
        f"/api/sessions/{session_id}/execute",
        json={"user_text": "请总结这份文件", "files": files},
    )
    assert execute.status_code == 200
    run_payload = execute.json()
    assert run_payload["status"] == "completed"
    assert run_payload["outputs"][0]["display_type"] == "text"
    assert_no_absolute_paths(run_payload["outputs"])

    fetched = client.get(
        f"/api/sessions/{session_id}/runs/{run_payload['run_id']}"
    )
    assert fetched.status_code == 200
    assert fetched.json()["run_id"] == run_payload["run_id"]


def test_api_document_qa_follow_up_reuses_current_workflow(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)
    session_id = create_session(client)
    files = upload_file(
        client,
        session_id,
        filename="sample_faq.md",
        content=(EXAMPLES_DIR / "sample_faq.md").read_bytes(),
    )
    first_question = "退款需要提供什么信息？"
    prepare = client.post(
        f"/api/sessions/{session_id}/prepare",
        json={"user_request": first_question, "files": files},
    )
    assert prepare.status_code == 200

    first_run = client.post(
        f"/api/sessions/{session_id}/execute",
        json={"user_text": first_question, "files": files},
    )
    assert first_run.status_code == 200
    second_run = client.post(
        f"/api/sessions/{session_id}/follow-up",
        json={"user_text": "会员支持方式有哪些？", "files": files},
    )
    assert second_run.status_code == 200
    assert second_run.json()["run_id"] != first_run.json()["run_id"]
    assert second_run.json()["version"] == first_run.json()["version"]
    assert_no_absolute_paths(second_run.json()["outputs"])


def test_api_feedback_creates_next_workflow_version(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)
    session_id = create_session(client)
    files = upload_file(
        client,
        session_id,
        filename="sample.txt",
        content=(EXAMPLES_DIR / "sample.txt").read_bytes(),
    )
    client.post(
        f"/api/sessions/{session_id}/prepare",
        json={"user_request": "请总结这份文件", "files": files},
    )
    execute = client.post(
        f"/api/sessions/{session_id}/execute",
        json={"user_text": "请总结这份文件", "files": files},
    )
    assert execute.status_code == 200

    feedback = client.post(
        f"/api/sessions/{session_id}/feedback",
        json={"feedback": "缩短到 80 字，保留 3 个要点"},
    )
    assert feedback.status_code == 200
    payload = feedback.json()
    assert payload["state"] == "AWAITING_CONFIRMATION"
    assert payload["debug"]["workflow"]["version"] == 2


def test_api_table_analysis_requires_csv_or_xlsx_before_execution(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)
    session_id = create_session(client)
    files = upload_file(
        client,
        session_id,
        filename="notes.md",
        content=b"# Not a table",
    )
    prepare = client.post(
        f"/api/sessions/{session_id}/prepare",
        json={"user_request": "表格分析", "files": files},
    )
    assert prepare.status_code == 200

    execute = client.post(
        f"/api/sessions/{session_id}/execute",
        json={"user_text": "表格分析", "files": files},
    )
    assert execute.status_code == 400
    assert "未找到可分析的表格文件" in execute.json()["detail"]


def test_api_upload_limits_are_session_cumulative(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)
    session_id = create_session(client)
    for index in range(10):
        response = client.post(
            f"/api/sessions/{session_id}/uploads",
            files=[("files", (f"file_{index}.txt", b"ok", "text/plain"))],
        )
        assert response.status_code == 200

    too_many = client.post(
        f"/api/sessions/{session_id}/uploads",
        files=[("files", ("file_10.txt", b"ok", "text/plain"))],
    )
    assert too_many.status_code == 400
    assert "最多只能上传 10 个文件" in too_many.json()["detail"]


def test_api_rejects_foreign_or_traversal_file_ref(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)
    session_id = create_session(client)
    bad_ref = {"id": "../sample.txt", "name": "sample.txt"}

    response = client.post(
        f"/api/sessions/{session_id}/prepare",
        json={"user_request": "请总结这份文件", "files": [bad_ref]},
    )

    assert response.status_code == 400
    assert "Invalid uploaded file reference" in response.json()["detail"]
