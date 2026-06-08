from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.orchestrator_state import (
    OrchestratorEvent,
    OrchestratorState,
    transition_state,
)
from core.workflow_schema import (
    BindingSource,
    DisplayType,
    InputBinding,
    ResultBinding,
    SourcePolicy,
    StepStatus,
    Workflow,
    WorkflowStatus,
)


def test_workflow_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Workflow.model_validate(
            {
                "id": "workflow_1",
                "version": 1,
                "goal": "Summarize a document",
                "source_policy": "uploaded_files_only",
                "workflow_inputs": [],
                "steps": [{"id": "read_1", "step_type": "read_document"}],
                "result_bindings": [
                    {
                        "step_id": "read_1",
                        "output_name": "documents",
                        "label": "Documents",
                        "display_type": "text",
                    }
                ],
                "unexpected": True,
            }
        )


def test_workflow_input_binding_requires_only_input_name() -> None:
    binding = InputBinding(
        source=BindingSource.WORKFLOW_INPUT,
        input_name="source_files",
    )
    assert binding.input_name == "source_files"

    with pytest.raises(ValidationError):
        InputBinding(
            source=BindingSource.WORKFLOW_INPUT,
            input_name="source_files",
            step_id="read_1",
        )


def test_step_output_binding_requires_step_and_output_names() -> None:
    binding = InputBinding(
        source=BindingSource.STEP_OUTPUT,
        step_id="read_1",
        output_name="documents",
    )
    assert binding.output_name == "documents"

    with pytest.raises(ValidationError):
        InputBinding(source=BindingSource.STEP_OUTPUT, step_id="read_1")


def test_result_binding_requires_display_metadata() -> None:
    binding = ResultBinding(
        step_id="generate_1",
        output_name="text",
        label="Summary",
        display_type=DisplayType.TEXT,
    )
    assert binding.label == "Summary"


def test_status_and_policy_enums_include_required_values() -> None:
    assert StepStatus.SKIPPED.value == "skipped"
    assert WorkflowStatus.VALIDATED.value == "validated"
    assert SourcePolicy.USER_PROVIDED_ONLY.value == "user_provided_only"


def test_orchestrator_state_transition_and_rejection() -> None:
    assert (
        transition_state(
            OrchestratorState.COLLECTING_REQUIREMENTS,
            OrchestratorEvent.WORKFLOW_READY,
        )
        == OrchestratorState.AWAITING_CONFIRMATION
    )
    with pytest.raises(ValueError, match="Unsupported orchestrator transition"):
        transition_state(
            OrchestratorState.COMPLETED,
            OrchestratorEvent.USER_CONFIRMED,
        )


def test_orchestrator_state_allows_new_run_after_completion() -> None:
    assert (
        transition_state(
            OrchestratorState.COMPLETED,
            OrchestratorEvent.USER_REQUESTED_NEW_RUN,
        )
        == OrchestratorState.RUNNING
    )


def test_orchestrator_state_allows_new_workflow_after_completion() -> None:
    assert (
        transition_state(
            OrchestratorState.COMPLETED,
            OrchestratorEvent.USER_REQUESTED_NEW_WORKFLOW,
        )
        == OrchestratorState.COLLECTING_REQUIREMENTS
    )
