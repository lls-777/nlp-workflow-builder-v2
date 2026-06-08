from __future__ import annotations

import pytest

from core.executor import execute_workflow, validate_workflow
from core.logging_utils import LOG_FILE
from core.workflow_schema import StepStatus, WorkflowStatus
from examples.run_document_qa_workflow import (
    HANDLER_MAP,
    create_context,
    load_workflow,
)
from tools.qa import REFUSAL_TEXT


@pytest.mark.parametrize(
    ("file_name", "question"),
    [
        (
            "document_qa.json",
            "What information is required for a member refund request?",
        ),
        ("faq_customer_service.json", "Can a member request a refund?"),
    ],
)
def test_document_qa_and_faq_workflows_execute_successfully(
    file_name: str,
    question: str,
) -> None:
    workflow = load_workflow(file_name)
    context = create_context(run_id=f"{file_name}_run", question=question)

    assert validate_workflow(workflow, context) == WorkflowStatus.VALIDATED
    result = execute_workflow(workflow, context, handler_map=HANDLER_MAP)

    assert result.status == WorkflowStatus.COMPLETED
    assert [step.status for step in result.step_runs] == [
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
    ]
    outputs = context.step_outputs[workflow.steps[-1].id]
    assert outputs["citations"]
    assert all("source_path" not in citation for citation in outputs["citations"])


def test_document_qa_workflow_refuses_unrelated_question() -> None:
    workflow = load_workflow("document_qa.json")
    context = create_context(
        run_id="document_qa_refusal_run",
        question="What is the office parking policy?",
    )

    result = execute_workflow(workflow, context, handler_map=HANDLER_MAP)

    assert result.status == WorkflowStatus.COMPLETED
    outputs = context.step_outputs["answer_qa_question"]
    assert outputs == {"text": REFUSAL_TEXT, "citations": []}


def test_document_qa_runtime_log_does_not_include_document_text_or_paths() -> None:
    workflow = load_workflow("document_qa.json")
    run_id = "document_qa_log_safety_run"
    context = create_context(
        run_id=run_id,
        question="Can a member request a refund?",
    )

    result = execute_workflow(workflow, context, handler_map=HANDLER_MAP)

    assert result.status == WorkflowStatus.COMPLETED
    matching_lines = [
        line
        for line in LOG_FILE.read_text(encoding="utf-8").splitlines()
        if f"run_id={run_id}" in line
    ]
    assert matching_lines
    assert all("Members can request a refund" not in line for line in matching_lines)
    assert all("/Users/" not in line for line in matching_lines)
