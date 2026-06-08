from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator

import pytest

from config import PROJECT_ROOT
from core.executor import validate_workflow
from core.step_registry import STEP_REGISTRY
from core.workflow_schema import Workflow, WorkflowStatus


WORKFLOW_DIR = PROJECT_ROOT / "examples" / "workflows"
WORKFLOW_FILES = (
    "summary.json",
    "document_qa.json",
    "data_analysis.json",
    "faq_customer_service.json",
    "one_time_report.json",
)


def load_payload(file_name: str) -> Dict[str, Any]:
    with (WORKFLOW_DIR / file_name).open(encoding="utf-8") as workflow_file:
        return json.load(workflow_file)


def load_workflow(file_name: str) -> Workflow:
    return Workflow.model_validate(load_payload(file_name))


def walk_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield key
            yield from walk_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from walk_keys(nested_value)


@pytest.mark.parametrize("file_name", WORKFLOW_FILES)
def test_acceptance_workflow_loads_and_passes_static_validation(
    file_name: str,
) -> None:
    workflow = load_workflow(file_name)

    assert validate_workflow(workflow) == WorkflowStatus.VALIDATED
    assert all(STEP_REGISTRY.get(step.step_type) is not None for step in workflow.steps)


@pytest.mark.parametrize(
    "file_name",
    ["document_qa.json", "faq_customer_service.json"],
)
def test_document_qa_and_faq_reuse_the_same_step_types(file_name: str) -> None:
    workflow = load_workflow(file_name)

    assert [step.step_type for step in workflow.steps] == [
        "read_document",
        "chunk_document",
        "retrieve_chunks",
        "answer_with_sources",
    ]


def test_faq_workflow_does_not_add_customer_service_specific_steps() -> None:
    workflow = load_workflow("faq_customer_service.json")

    assert all(
        step.step_type not in {"customer_service_agent", "customer_service_tool"}
        for step in workflow.steps
    )


def test_data_analysis_uses_only_declarative_params() -> None:
    payload = load_payload("data_analysis.json")
    forbidden_fields = {"code", "python", "eval", "exec", "pandas_expression"}

    assert forbidden_fields.isdisjoint(set(walk_keys(payload)))


def test_one_time_report_has_no_background_repetition_configuration() -> None:
    payload = load_payload("one_time_report.json")
    serialized_payload = json.dumps(payload).lower()

    for forbidden_term in ("schedule", "cron", "timer", "recurrence", "定时"):
        assert forbidden_term not in serialized_payload
