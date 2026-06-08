from __future__ import annotations

from enum import Enum
from typing import Dict, Tuple


class OrchestratorState(str, Enum):
    COLLECTING_REQUIREMENTS = "COLLECTING_REQUIREMENTS"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVISING = "REVISING"
    UNSUPPORTED = "UNSUPPORTED"


class OrchestratorEvent(str, Enum):
    NEEDS_MORE_INFO = "needs_more_info"
    WORKFLOW_READY = "workflow_ready"
    USER_CONFIRMED = "user_confirmed"
    EXECUTION_SUCCEEDED = "execution_succeeded"
    EXECUTION_FAILED = "execution_failed"
    USER_REQUESTED_CHANGE = "user_requested_change"
    USER_RETRY_REQUESTED = "user_retry_requested"
    USER_REQUESTED_NEW_RUN = "user_requested_new_run"
    USER_REQUESTED_NEW_WORKFLOW = "user_requested_new_workflow"
    UNSUPPORTED_REQUEST = "unsupported_request"
    USER_REFRAMED_REQUEST = "user_reframed_request"


TransitionKey = Tuple[OrchestratorState, OrchestratorEvent]

TRANSITIONS: Dict[TransitionKey, OrchestratorState] = {
    (
        OrchestratorState.COLLECTING_REQUIREMENTS,
        OrchestratorEvent.NEEDS_MORE_INFO,
    ): OrchestratorState.COLLECTING_REQUIREMENTS,
    (
        OrchestratorState.COLLECTING_REQUIREMENTS,
        OrchestratorEvent.WORKFLOW_READY,
    ): OrchestratorState.AWAITING_CONFIRMATION,
    (
        OrchestratorState.COLLECTING_REQUIREMENTS,
        OrchestratorEvent.UNSUPPORTED_REQUEST,
    ): OrchestratorState.UNSUPPORTED,
    (
        OrchestratorState.AWAITING_CONFIRMATION,
        OrchestratorEvent.USER_CONFIRMED,
    ): OrchestratorState.RUNNING,
    (
        OrchestratorState.RUNNING,
        OrchestratorEvent.EXECUTION_SUCCEEDED,
    ): OrchestratorState.COMPLETED,
    (
        OrchestratorState.RUNNING,
        OrchestratorEvent.EXECUTION_FAILED,
    ): OrchestratorState.FAILED,
    (
        OrchestratorState.COMPLETED,
        OrchestratorEvent.USER_REQUESTED_CHANGE,
    ): OrchestratorState.REVISING,
    (
        OrchestratorState.FAILED,
        OrchestratorEvent.USER_REQUESTED_CHANGE,
    ): OrchestratorState.REVISING,
    (
        OrchestratorState.REVISING,
        OrchestratorEvent.WORKFLOW_READY,
    ): OrchestratorState.AWAITING_CONFIRMATION,
    (
        OrchestratorState.FAILED,
        OrchestratorEvent.USER_RETRY_REQUESTED,
    ): OrchestratorState.RUNNING,
    (
        OrchestratorState.COMPLETED,
        OrchestratorEvent.USER_REQUESTED_NEW_RUN,
    ): OrchestratorState.RUNNING,
    (
        OrchestratorState.COMPLETED,
        OrchestratorEvent.USER_REQUESTED_NEW_WORKFLOW,
    ): OrchestratorState.COLLECTING_REQUIREMENTS,
    (
        OrchestratorState.FAILED,
        OrchestratorEvent.USER_REQUESTED_NEW_WORKFLOW,
    ): OrchestratorState.COLLECTING_REQUIREMENTS,
    (
        OrchestratorState.UNSUPPORTED,
        OrchestratorEvent.USER_REFRAMED_REQUEST,
    ): OrchestratorState.COLLECTING_REQUIREMENTS,
}


def transition_state(
    state: OrchestratorState, event: OrchestratorEvent
) -> OrchestratorState:
    try:
        return TRANSITIONS[(state, event)]
    except KeyError as exc:
        raise ValueError(
            "Unsupported orchestrator transition: "
            f"{state.value} --{event.value}--> ?"
        ) from exc
