from __future__ import annotations

from pathlib import Path

import pytest

from config import EXAMPLES_DIR
from core.orchestrator import Orchestrator
from core.orchestrator_state import OrchestratorState
from core.workflow_schema import WorkflowStatus
from storage.file_store import FileStore
from storage.sqlite_store import SQLiteStore


def create_orchestrator(tmp_path: Path) -> Orchestrator:
    uploads_dir = tmp_path / "uploads"
    artifacts_dir = tmp_path / "artifacts"
    return Orchestrator(
        store=SQLiteStore(tmp_path / "app.db"),
        file_store=FileStore(
            uploads_dir=uploads_dir,
            artifacts_dir=artifacts_dir,
            allowed_source_roots=(EXAMPLES_DIR, uploads_dir),
        ),
    )


def test_orchestrator_records_summary_run_and_step_runs(tmp_path: Path) -> None:
    orchestrator = create_orchestrator(tmp_path)
    orchestrator.create_session("session_1")
    prepared = orchestrator.prepare_workflow(
        session_id="session_1",
        user_request="请总结这份文件",
        uploaded_files=[EXAMPLES_DIR / "sample.txt"],
    )

    assert prepared.state == OrchestratorState.AWAITING_CONFIRMATION
    result = orchestrator.confirm_and_execute(
        session_id="session_1",
        workflow_inputs={"source_files": [str(EXAMPLES_DIR / "sample.txt")]},
    )

    assert result.status == WorkflowStatus.COMPLETED
    assert orchestrator.store.get_session("session_1")["state"] == (
        OrchestratorState.COMPLETED.value
    )
    runs = orchestrator.store.list_runs("session_1")
    assert len(runs) == 1
    assert len(orchestrator.store.list_step_runs(runs[0]["run_id"])) == 2


def test_orchestrator_feedback_creates_version_two_and_full_rerun(
    tmp_path: Path,
) -> None:
    orchestrator = create_orchestrator(tmp_path)
    orchestrator.create_session("session_1")
    prepared = orchestrator.prepare_workflow(
        session_id="session_1",
        user_request="请总结这份文件",
        uploaded_files=[EXAMPLES_DIR / "sample.txt"],
    )
    orchestrator.confirm_and_execute(
        session_id="session_1",
        workflow_inputs={"source_files": [str(EXAMPLES_DIR / "sample.txt")]},
    )

    revised = orchestrator.revise_current_workflow(
        session_id="session_1",
        feedback="缩短到 80 字，保留 3 个要点",
    )

    assert revised.plan is not None
    assert revised.plan.workflow.id == prepared.plan.workflow.id
    assert revised.plan.workflow.version == 2
    rerun = orchestrator.confirm_and_execute(
        session_id="session_1",
        workflow_inputs={"source_files": [str(EXAMPLES_DIR / "sample.txt")]},
    )
    assert rerun.status == WorkflowStatus.COMPLETED
    assert len(orchestrator.store.list_workflow_versions("session_1")) == 2
    assert len(orchestrator.store.list_runs("session_1")) == 2


def test_new_document_question_reuses_version_and_creates_new_run(
    tmp_path: Path,
) -> None:
    orchestrator = create_orchestrator(tmp_path)
    orchestrator.create_session("session_1")
    prepared = orchestrator.prepare_workflow(
        session_id="session_1",
        user_request="What do users value?",
        uploaded_files=[EXAMPLES_DIR / "sample.txt"],
    )
    assert prepared.plan is not None

    first_result = orchestrator.confirm_and_execute(
        session_id="session_1",
        workflow_inputs={
            "source_files": [str(EXAMPLES_DIR / "sample.txt")],
            "question": "What do users value?",
        },
    )
    second_result = orchestrator.run_current_workflow(
        session_id="session_1",
        workflow_inputs={
            "source_files": [str(EXAMPLES_DIR / "sample.txt")],
            "question": "What should the first release keep simple?",
        },
    )

    assert first_result.status == WorkflowStatus.COMPLETED
    assert second_result.status == WorkflowStatus.COMPLETED
    versions = orchestrator.store.list_workflow_versions("session_1")
    runs = orchestrator.store.list_runs("session_1")
    assert len(versions) == 1
    assert len(runs) == 2
    assert {run["workflow_version"] for run in runs} == {1}


def test_orchestrator_weekly_report_requires_one_time_fallback_acceptance(
    tmp_path: Path,
) -> None:
    orchestrator = create_orchestrator(tmp_path)
    orchestrator.create_session("session_1")
    unsupported = orchestrator.prepare_workflow(
        session_id="session_1",
        user_request="请每周一自动生成报告",
        uploaded_files=[EXAMPLES_DIR / "sample.txt"],
    )

    assert unsupported.state == OrchestratorState.UNSUPPORTED
    assert "暂不支持" in unsupported.message

    accepted = orchestrator.accept_one_time_report(
        session_id="session_1",
        user_request="接受立即生成一次报告",
        uploaded_files=[EXAMPLES_DIR / "sample.txt"],
    )
    assert accepted.state == OrchestratorState.AWAITING_CONFIRMATION
    assert accepted.plan is not None
    serialized_workflow = accepted.plan.workflow.model_dump_json().lower()
    for forbidden_term in ("schedule", "cron", "timer", "recurrence", "定时"):
        assert forbidden_term not in serialized_workflow


def test_orchestrator_web_facade_saves_upload_builds_inputs_and_presents_result(
    tmp_path: Path,
) -> None:
    orchestrator = create_orchestrator(tmp_path)
    orchestrator.create_session("session_1")
    stored_path = orchestrator.save_upload(
        original_filename="notes.txt",
        content=b"Users value clear setup instructions and a simple visible workflow.",
    )
    orchestrator.prepare_workflow(
        session_id="session_1",
        user_request="请总结这份文件",
        uploaded_files=[stored_path],
    )

    runtime_inputs = orchestrator.build_runtime_inputs(
        session_id="session_1",
        uploaded_files=[stored_path],
        user_text="请总结这份文件",
    )
    result = orchestrator.execute_prepared_workflow(
        session_id="session_1",
        uploaded_files=[stored_path],
        user_text="请总结这份文件",
    )
    presentation = orchestrator.present_result(result)

    assert runtime_inputs == {"source_files": [str(stored_path)]}
    assert presentation.status == WorkflowStatus.COMPLETED.value
    assert presentation.version == 1
    assert presentation.outputs[0].display_type == "text"
    assert presentation.outputs[0].value.startswith("Summary:")
    assert [activity.status for activity in presentation.activities] == [
        "completed",
        "completed",
    ]


def test_orchestrator_web_facade_presents_document_answer_and_citations(
    tmp_path: Path,
) -> None:
    orchestrator = create_orchestrator(tmp_path)
    orchestrator.create_session("session_1")
    stored_path = orchestrator.save_upload(
        original_filename="faq.md",
        content=(EXAMPLES_DIR / "sample_faq.md").read_bytes(),
    )
    orchestrator.prepare_workflow(
        session_id="session_1",
        user_request="Can a member request a refund?",
        uploaded_files=[stored_path],
    )

    result = orchestrator.execute_prepared_workflow(
        session_id="session_1",
        uploaded_files=[stored_path],
        user_text="Can a member request a refund?",
    )
    presentation = orchestrator.present_result(result)

    assert presentation.status == WorkflowStatus.COMPLETED.value
    assert [output.display_type for output in presentation.outputs] == [
        "text",
        "citations",
    ]
    citations = presentation.outputs[1].value
    assert citations
    assert citations[0]["source_name"].endswith(".md")
    assert "source_path" not in citations[0]


def test_orchestrator_web_facade_presents_table_chart_and_insights(
    tmp_path: Path,
) -> None:
    orchestrator = create_orchestrator(tmp_path)
    orchestrator.create_session("session_1")
    stored_path = orchestrator.save_upload(
        original_filename="sales.csv",
        content=(EXAMPLES_DIR / "sample_sales.csv").read_bytes(),
    )
    orchestrator.prepare_workflow(
        session_id="session_1",
        user_request="请分析销售数据",
        uploaded_files=[stored_path],
    )

    result = orchestrator.execute_prepared_workflow(
        session_id="session_1",
        uploaded_files=[stored_path],
        user_text="请分析销售数据",
    )
    presentation = orchestrator.present_result(result)

    assert presentation.status == WorkflowStatus.COMPLETED.value
    assert [output.display_type for output in presentation.outputs] == [
        "table",
        "chart",
        "text",
    ]
    assert presentation.outputs[0].value["records"]
    assert presentation.outputs[1].value["chart_type"] == "bar"
    assert presentation.outputs[2].value.startswith("Business insights:")


def test_completed_session_can_prepare_new_document_question(
    tmp_path: Path,
) -> None:
    orchestrator = create_orchestrator(tmp_path)
    orchestrator.create_session("session_1")
    summary_path = orchestrator.save_upload(
        original_filename="notes.txt",
        content=b"Users value clear setup instructions.",
    )
    orchestrator.prepare_new_request(
        session_id="session_1",
        user_request="请总结这份文件",
        uploaded_files=[summary_path],
    )
    orchestrator.execute_prepared_workflow(
        session_id="session_1",
        uploaded_files=[summary_path],
        user_text="请总结这份文件",
    )
    faq_path = orchestrator.save_upload(
        original_filename="faq.md",
        content=(EXAMPLES_DIR / "sample_faq.md").read_bytes(),
    )

    prepared = orchestrator.prepare_new_request(
        session_id="session_1",
        user_request="退款需要提供什么信息？",
        uploaded_files=[faq_path],
    )

    assert prepared.state == OrchestratorState.AWAITING_CONFIRMATION
    assert prepared.plan is not None
    assert [step.step_type for step in prepared.plan.workflow.steps] == [
        "read_document",
        "chunk_document",
        "retrieve_chunks",
        "answer_with_sources",
    ]


def test_table_analysis_requires_csv_or_xlsx_before_execution(
    tmp_path: Path,
) -> None:
    orchestrator = create_orchestrator(tmp_path)
    orchestrator.create_session("session_1")
    text_path = orchestrator.save_upload(
        original_filename="notes.txt",
        content=b"Not a table.",
    )
    faq_path = orchestrator.save_upload(
        original_filename="faq.md",
        content=(EXAMPLES_DIR / "sample_faq.md").read_bytes(),
    )
    orchestrator.prepare_new_request(
        session_id="session_1",
        user_request="表格分析",
        uploaded_files=[text_path, faq_path],
    )

    with pytest.raises(
        ValueError,
        match="未找到可分析的表格文件，请上传 CSV 或 XLSX 文件",
    ):
        orchestrator.execute_prepared_workflow(
            session_id="session_1",
            uploaded_files=[text_path, faq_path],
            user_text="表格分析",
        )

    assert orchestrator.store.list_runs("session_1") == []
