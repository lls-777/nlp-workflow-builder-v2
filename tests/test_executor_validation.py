from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterator
from uuid import uuid4

import pytest

from config import EXAMPLES_DIR, MAX_WORKFLOW_STEPS
from core.executor import WorkflowValidationError, execute_workflow, validate_workflow
from core.step_registry import STEP_REGISTRY
from core.workflow_schema import (
    ExecutionContext,
    SourcePolicy,
    StepStatus,
    Workflow,
    WorkflowStatus,
)


def summary_payload() -> Dict[str, Any]:
    return {
        "id": "summary_workflow",
        "version": 1,
        "goal": "Generate a short summary",
        "source_policy": "uploaded_files_only",
        "workflow_inputs": [
            {"name": "source_files", "value_type": "files", "required": True}
        ],
        "steps": [
            {
                "id": "read_1",
                "step_type": "read_document",
                "inputs": [
                    {
                        "name": "files",
                        "bindings": [
                            {
                                "source": "workflow_input",
                                "input_name": "source_files",
                            }
                        ],
                    }
                ],
                "params": {},
            },
            {
                "id": "generate_1",
                "step_type": "generate_text",
                "inputs": [
                    {
                        "name": "materials",
                        "bindings": [
                            {
                                "source": "step_output",
                                "step_id": "read_1",
                                "output_name": "documents",
                            }
                        ],
                    }
                ],
                "params": {"task": "summary", "bullet_count": 3},
            },
        ],
        "result_bindings": [
            {
                "step_id": "generate_1",
                "output_name": "text",
                "label": "Summary",
                "display_type": "text",
            }
        ],
    }


@pytest.fixture
def allowed_text_file() -> Iterator[Path]:
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    path = EXAMPLES_DIR / f".validation_{uuid4().hex}.txt"
    path.write_text("A local document used by executor validation tests.", encoding="utf-8")
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def context_for(path: Path) -> ExecutionContext:
    return ExecutionContext(
        session_id="session_1",
        run_id="run_1",
        workflow_inputs={"source_files": [str(path)]},
    )


def test_validate_workflow_accepts_valid_linear_workflow(
    allowed_text_file: Path,
) -> None:
    workflow = Workflow.model_validate(summary_payload())
    assert validate_workflow(workflow, context_for(allowed_text_file)) == (
        WorkflowStatus.VALIDATED
    )


def test_validate_workflow_rejects_duplicate_step_ids() -> None:
    payload = summary_payload()
    payload["steps"][1]["id"] = "read_1"
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="Duplicate step ids"):
        validate_workflow(workflow)


def test_validate_workflow_rejects_duplicate_workflow_input_names() -> None:
    payload = summary_payload()
    payload["workflow_inputs"].append(
        {"name": "source_files", "value_type": "files", "required": True}
    )
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="Duplicate workflow input names"):
        validate_workflow(workflow)


def test_validate_workflow_rejects_unregistered_step_type() -> None:
    payload = summary_payload()
    payload["steps"][0]["step_type"] = "invented_step"
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="Unregistered step_type"):
        validate_workflow(workflow)


def test_validate_workflow_rejects_disabled_step_type() -> None:
    payload = summary_payload()
    payload["steps"][0]["step_type"] = "web_search"
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="Disabled step_type"):
        validate_workflow(workflow)


def test_validate_workflow_rejects_unknown_params() -> None:
    payload = summary_payload()
    payload["steps"][0]["params"] = {"unexpected": True}
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="Invalid params"):
        validate_workflow(workflow)


def test_validate_workflow_rejects_missing_required_input_port() -> None:
    payload = summary_payload()
    payload["steps"][0]["inputs"] = []
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="missing required input ports"):
        validate_workflow(workflow)


def test_validate_workflow_rejects_incompatible_input_type() -> None:
    payload = summary_payload()
    payload["workflow_inputs"][0]["value_type"] = "text"
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="expects"):
        validate_workflow(workflow)


def test_validate_workflow_rejects_forward_step_reference() -> None:
    payload = summary_payload()
    payload["steps"] = [payload["steps"][1], payload["steps"][0]]
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="must reference a previous step"):
        validate_workflow(workflow)


def test_validate_workflow_rejects_unknown_step_output() -> None:
    payload = summary_payload()
    payload["steps"][1]["inputs"][0]["bindings"][0]["output_name"] = "missing"
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="references unknown output"):
        validate_workflow(workflow)


def test_validate_workflow_rejects_unknown_result_output() -> None:
    payload = summary_payload()
    payload["result_bindings"][0]["output_name"] = "missing"
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="Result binding references unknown"):
        validate_workflow(workflow)


@pytest.mark.parametrize(
    "policy",
    [
        SourcePolicy.UPLOADED_FILES_ONLY.value,
        SourcePolicy.USER_PROVIDED_ONLY.value,
    ],
)
def test_validate_workflow_rejects_network_step_for_offline_policy(
    policy: str,
) -> None:
    payload = {
        "id": "search_workflow",
        "version": 1,
        "goal": "Answer with external sources",
        "source_policy": policy,
        "workflow_inputs": [
            {"name": "question", "value_type": "text", "required": True}
        ],
        "steps": [
            {
                "id": "search_1",
                "step_type": "web_search",
                "inputs": [
                    {
                        "name": "query",
                        "bindings": [
                            {
                                "source": "workflow_input",
                                "input_name": "question",
                            }
                        ],
                    }
                ],
                "params": {},
            },
            {
                "id": "answer_1",
                "step_type": "answer_with_sources",
                "inputs": [
                    {
                        "name": "retrieved_chunks",
                        "bindings": [
                            {
                                "source": "step_output",
                                "step_id": "search_1",
                                "output_name": "retrieved_chunks",
                            }
                        ],
                    },
                    {
                        "name": "question",
                        "bindings": [
                            {
                                "source": "workflow_input",
                                "input_name": "question",
                            }
                        ],
                    },
                ],
                "params": {},
            },
        ],
        "result_bindings": [
            {
                "step_id": "answer_1",
                "output_name": "text",
                "label": "Answer",
                "display_type": "text",
            }
        ],
    }
    registry = STEP_REGISTRY.clone_with("web_search", enabled=True)
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="forbids network step"):
        validate_workflow(workflow, registry=registry)


def test_validate_workflow_rejects_system_file_path() -> None:
    workflow = Workflow.model_validate(summary_payload())
    with pytest.raises(WorkflowValidationError, match="outside allowed upload roots"):
        validate_workflow(workflow, context_for(Path("/etc/hosts")))


def test_validate_workflow_rejects_path_traversal() -> None:
    workflow = Workflow.model_validate(summary_payload())
    traversal_path = EXAMPLES_DIR / ".." / ".." / "etc" / "hosts"
    with pytest.raises(WorkflowValidationError, match="outside allowed upload roots"):
        validate_workflow(workflow, context_for(traversal_path))


def test_validate_workflow_rejects_symlink_escape(tmp_path: Path) -> None:
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("outside allowed roots", encoding="utf-8")
    link = EXAMPLES_DIR / f".outside_link_{uuid4().hex}.txt"
    os.symlink(outside_file, link)
    try:
        workflow = Workflow.model_validate(summary_payload())
        with pytest.raises(WorkflowValidationError, match="outside allowed upload roots"):
            validate_workflow(workflow, context_for(link))
    finally:
        link.unlink(missing_ok=True)


def test_validate_workflow_rejects_step_limit() -> None:
    payload = summary_payload()
    payload["steps"] = [
        {
            "id": f"read_{index}",
            "step_type": "read_document",
            "inputs": payload["steps"][0]["inputs"],
            "params": {},
        }
        for index in range(MAX_WORKFLOW_STEPS + 1)
    ]
    workflow = Workflow.model_validate(payload)
    with pytest.raises(WorkflowValidationError, match="limit is"):
        validate_workflow(workflow)


def test_execute_workflow_runs_placeholder_handlers_in_order(
    allowed_text_file: Path,
) -> None:
    workflow = Workflow.model_validate(summary_payload())
    context = context_for(allowed_text_file)

    def read_handler(
        inputs: Dict[str, Any], params: Dict[str, Any], run_context: ExecutionContext
    ) -> Dict[str, Any]:
        assert inputs["files"] == [str(allowed_text_file)]
        assert params == {}
        return {"documents": ["Document text"]}

    def generate_handler(
        inputs: Dict[str, Any], params: Dict[str, Any], run_context: ExecutionContext
    ) -> Dict[str, Any]:
        assert inputs["materials"] == ["Document text"]
        assert params["task"] == "summary"
        return {"text": "Short summary"}

    result = execute_workflow(
        workflow,
        context,
        handler_map={
            "read_document": read_handler,
            "generate_text": generate_handler,
        },
    )

    assert result.status == WorkflowStatus.COMPLETED
    assert [step.status for step in result.step_runs] == [
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
    ]
    assert result.final_outputs[0].preview == "Short summary"
    assert result.final_outputs[0].label == "Summary"
    assert result.final_outputs[0].display_type.value == "text"
    assert result.final_outputs[0].value == "Short summary"


def test_execute_workflow_marks_remaining_steps_skipped_after_failure(
    allowed_text_file: Path,
) -> None:
    payload = summary_payload()
    payload["steps"].append(
        {
            "id": "generate_2",
            "step_type": "generate_text",
            "inputs": [
                {
                    "name": "materials",
                    "bindings": [
                        {
                            "source": "step_output",
                            "step_id": "generate_1",
                            "output_name": "text",
                        }
                    ],
                }
            ],
            "params": {"task": "summary"},
        }
    )
    payload["result_bindings"][0]["step_id"] = "generate_2"
    workflow = Workflow.model_validate(payload)

    def read_handler(
        inputs: Dict[str, Any], params: Dict[str, Any], run_context: ExecutionContext
    ) -> Dict[str, Any]:
        return {"documents": ["Document text"]}

    def failing_handler(
        inputs: Dict[str, Any], params: Dict[str, Any], run_context: ExecutionContext
    ) -> Dict[str, Any]:
        raise RuntimeError("Text generation failed")

    result = execute_workflow(
        workflow,
        context_for(allowed_text_file),
        handler_map={
            "read_document": read_handler,
            "generate_text": failing_handler,
        },
    )

    assert result.status == WorkflowStatus.FAILED
    assert [step.status for step in result.step_runs] == [
        StepStatus.COMPLETED,
        StepStatus.FAILED,
        StepStatus.SKIPPED,
    ]
    assert result.error_message == "Text generation failed"
