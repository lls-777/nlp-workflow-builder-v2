from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.orchestrator_state import OrchestratorState
from core.workflow_schema import (
    StepOutput,
    StepRunResult,
    StepStatus,
    ValueType,
    Workflow,
    WorkflowResult,
    WorkflowStatus,
)
from storage.sqlite_store import SQLiteStore


def load_summary_workflow() -> Workflow:
    workflow_path = Path(__file__).parents[1] / "examples" / "workflows" / "summary.json"
    return Workflow.model_validate_json(workflow_path.read_text(encoding="utf-8"))


def test_sqlite_store_creates_only_four_tables_and_session(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "app.db")

    session = store.create_session("session_1")

    assert store.list_tables() == [
        "runs",
        "sessions",
        "step_runs",
        "workflow_versions",
    ]
    assert session["session_id"] == "session_1"
    assert session["state"] == OrchestratorState.COLLECTING_REQUIREMENTS.value


def test_sqlite_store_saves_and_reads_workflow_version(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "app.db")
    store.create_session("session_1")
    workflow = load_summary_workflow()

    store.save_workflow_version(
        session_id="session_1",
        workflow=workflow,
        plan_text="Read the files and summarize them.",
        user_request="Summarize this file.",
    )

    assert store.get_current_workflow("session_1") == workflow
    assert store.get_workflow_version(workflow.id, workflow.version) == workflow
    versions = store.list_workflow_versions("session_1")
    assert [(item["workflow_id"], item["version"]) for item in versions] == [
        (workflow.id, 1)
    ]


def test_sqlite_store_saves_run_and_step_runs(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "app.db")
    store.create_session("session_1")
    workflow = load_summary_workflow()
    store.save_workflow_version(
        session_id="session_1",
        workflow=workflow,
        plan_text="Read and summarize.",
        user_request="Summarize this file.",
    )
    run_id = store.create_run(
        session_id="session_1",
        workflow=workflow,
        workflow_inputs={"source_files": [Path("examples/sample.txt")]},
        run_id="run_1",
    )
    now = datetime.now(timezone.utc)
    result = WorkflowResult(
        workflow_id=workflow.id,
        workflow_version=workflow.version,
        run_id=run_id,
        status=WorkflowStatus.COMPLETED,
        step_runs=[
            StepRunResult(
                step_id="generate_summary",
                step_type="generate_text",
                status=StepStatus.COMPLETED,
                outputs=[
                    StepOutput(
                        output_name="text",
                        value_type=ValueType.TEXT,
                        preview="Short summary",
                    )
                ],
                preview="Short summary",
                started_at=now,
                finished_at=now,
            )
        ],
    )

    store.save_run_result(result)

    stored_run = store.get_run(run_id)
    assert stored_run["status"] == WorkflowStatus.COMPLETED.value
    assert stored_run["inputs_json"] == {"source_files": ["examples/sample.txt"]}
    assert stored_run["result_json"]["run_id"] == run_id
    step_runs = store.list_step_runs(run_id)
    assert len(step_runs) == 1
    assert step_runs[0]["step_id"] == "generate_summary"
    assert step_runs[0]["outputs_json"][0]["preview"] == "Short summary"
