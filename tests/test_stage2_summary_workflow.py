from __future__ import annotations

from pathlib import Path

import pytest

from core.executor import execute_workflow, validate_workflow
from core.llm import LLMSettings, MockLLMClient, get_llm_client
from core.logging_utils import LOG_FILE, log_step_status
from core.workflow_schema import StepStatus, WorkflowStatus
from examples.run_demo_workflow import create_demo_context, load_demo_workflow
from tools.documents import DocumentReadError, read_document_file
from tools.documents import read_document as read_document_handler
from tools.text_generation import generate_text


def test_read_txt_document_successfully(tmp_path: Path) -> None:
    document = tmp_path / "notes.txt"
    document.write_text("TXT document content.", encoding="utf-8")

    result = read_document_file(document)

    assert result["name"] == "notes.txt"
    assert result["content"] == "TXT document content."


def test_read_md_document_successfully(tmp_path: Path) -> None:
    document = tmp_path / "notes.md"
    document.write_text("# Notes\n\nMarkdown content.", encoding="utf-8")

    result = read_document_file(document)

    assert result["name"] == "notes.md"
    assert result["content"] == "# Notes\n\nMarkdown content."


def test_unsupported_document_format_returns_clear_message(tmp_path: Path) -> None:
    document = tmp_path / "unsupported.rtf"
    document.write_bytes(b"placeholder")

    with pytest.raises(DocumentReadError, match="Supported formats"):
        read_document_file(document)


def test_mock_text_generation_is_stable() -> None:
    client = MockLLMClient()
    materials = [
        {
            "content": (
                "The first sentence is the summary. "
                "The second sentence is a key point. "
                "The third sentence is another key point."
            )
        }
    ]

    first = client.generate_text(task="summary", materials=materials, bullet_count=2)
    second = client.generate_text(task="summary", materials=materials, bullet_count=2)

    assert first == second
    assert first == (
        "Summary:\n"
        "The first sentence is the summary.\n\n"
        "Key points:\n"
        "- The first sentence is the summary.\n"
        "- The second sentence is a key point."
    )


def test_llm_defaults_to_mock_mode() -> None:
    client = get_llm_client(LLMSettings())
    assert isinstance(client, MockLLMClient)


def test_demo_summary_workflow_validates_and_executes() -> None:
    workflow = load_demo_workflow()
    context = create_demo_context()

    assert validate_workflow(workflow, context) == WorkflowStatus.VALIDATED

    result = execute_workflow(
        workflow,
        context,
        handler_map={
            "read_document": read_document_handler,
            "generate_text": generate_text,
        },
    )

    assert result.status == WorkflowStatus.COMPLETED
    assert [step.status for step in result.step_runs] == [
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
    ]
    assert context.step_outputs["generate_1"]["text"].startswith("Summary:")


def test_runtime_log_redacts_sensitive_error_values() -> None:
    marker = "stage2_redaction_check"
    sensitive_value = "placeholder-sensitive-value"

    log_step_status(
        workflow_id=marker,
        run_id="redaction_run",
        step_id="generate_1",
        step_type="generate_text",
        status=StepStatus.FAILED,
        error_summary=f"api_key={sensitive_value}",
    )

    matching_line = next(
        line
        for line in reversed(LOG_FILE.read_text(encoding="utf-8").splitlines())
        if marker in line
    )
    assert "api_key=[REDACTED]" in matching_line
    assert sensitive_value not in matching_line
