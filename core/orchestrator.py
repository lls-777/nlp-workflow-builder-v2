from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Union

from core.executor import Handler, execute_workflow
from core.orchestrator_state import (
    OrchestratorEvent,
    OrchestratorState,
    transition_state,
)
from core.planner import Clarification, PlannedWorkflow, Planner, Scenario
from core.workflow_schema import (
    ExecutionContext,
    ValueType,
    WorkflowResult,
    WorkflowStatus,
)
from storage.file_store import FileStore
from storage.sqlite_store import SQLiteStore, SQLiteStoreError
from tools.data_analysis import (
    aggregate_table,
    filter_table,
    profile_table,
    read_table,
    render_chart,
    sort_table,
)
from tools.documents import read_document
from tools.qa import answer_with_sources
from tools.retrieval import chunk_document, retrieve_chunks
from tools.text_generation import generate_text


DEFAULT_HANDLER_MAP: Dict[str, Handler] = {
    "read_document": read_document,
    "chunk_document": chunk_document,
    "retrieve_chunks": retrieve_chunks,
    "answer_with_sources": answer_with_sources,
    "read_table": read_table,
    "profile_table": profile_table,
    "filter_table": filter_table,
    "aggregate_table": aggregate_table,
    "sort_table": sort_table,
    "render_chart": render_chart,
    "generate_text": generate_text,
}
ACTIVITY_LABELS = {
    "read_document": "读取文件内容",
    "chunk_document": "整理文件片段",
    "retrieve_chunks": "查找相关内容",
    "answer_with_sources": "根据文件回答并附上依据",
    "read_table": "读取表格",
    "profile_table": "概览表格结构",
    "filter_table": "筛选符合条件的数据",
    "aggregate_table": "汇总关键指标",
    "sort_table": "整理结果顺序",
    "render_chart": "准备图表",
    "generate_text": "生成文字结果",
}


@dataclass(frozen=True)
class OrchestratorResponse:
    session_id: str
    state: OrchestratorState
    message: Optional[str] = None
    questions: Tuple[str, ...] = ()
    plan: Optional[PlannedWorkflow] = None


@dataclass(frozen=True)
class PresentedOutput:
    label: str
    display_type: str
    value: Any


@dataclass(frozen=True)
class ActivitySummary:
    title: str
    status: str
    error_message: Optional[str] = None


@dataclass(frozen=True)
class RunPresentation:
    version: int
    status: str
    outputs: Tuple[PresentedOutput, ...]
    activities: Tuple[ActivitySummary, ...]
    error_message: Optional[str] = None


class Orchestrator:
    """Single state coordinator for planning, execution, and local records."""

    def __init__(
        self,
        *,
        store: Optional[SQLiteStore] = None,
        file_store: Optional[FileStore] = None,
        planner: Optional[Planner] = None,
        handler_map: Optional[Mapping[str, Handler]] = None,
    ) -> None:
        self.store = store or SQLiteStore()
        self.file_store = file_store or FileStore()
        self.planner = planner or Planner()
        self.handler_map = dict(handler_map or DEFAULT_HANDLER_MAP)

    def create_session(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        return self.store.create_session(session_id)

    def save_upload(self, *, original_filename: str, content: bytes) -> Path:
        return self.file_store.save_upload(
            original_filename=original_filename,
            content=content,
        )

    def save_uploads(
        self,
        *,
        uploads: Sequence[Tuple[str, bytes]],
        existing_paths: Sequence[Union[str, Path]] = (),
    ) -> Sequence[Path]:
        return self.file_store.save_uploads(
            uploads=uploads,
            existing_paths=existing_paths,
        )

    def build_runtime_inputs(
        self,
        *,
        session_id: str,
        uploaded_files: Sequence[Union[str, Path]],
        user_text: str,
    ) -> Dict[str, Any]:
        workflow = self.store.get_current_workflow(session_id)
        resolved_files = [
            str(path) for path in self.file_store.resolve_uploads(uploaded_files)
        ]
        runtime_inputs: Dict[str, Any] = {}
        for workflow_input in workflow.workflow_inputs:
            if workflow_input.value_type == ValueType.FILES:
                runtime_inputs[workflow_input.name] = resolved_files
            elif workflow_input.value_type == ValueType.FILE:
                if not resolved_files:
                    raise ValueError("请先上传需要处理的文件。")
                table_files = [
                    path
                    for path in resolved_files
                    if Path(path).suffix.lower() in {".csv", ".xlsx"}
                ]
                if not table_files:
                    raise ValueError(
                        "未找到可分析的表格文件，请上传 CSV 或 XLSX 文件。"
                    )
                runtime_inputs[workflow_input.name] = table_files[0]
            elif workflow_input.value_type == ValueType.TEXT:
                runtime_inputs[workflow_input.name] = user_text
        return runtime_inputs

    def execute_prepared_workflow(
        self,
        *,
        session_id: str,
        uploaded_files: Sequence[Union[str, Path]],
        user_text: str,
    ) -> WorkflowResult:
        return self.confirm_and_execute(
            session_id=session_id,
            workflow_inputs=self.build_runtime_inputs(
                session_id=session_id,
                uploaded_files=uploaded_files,
                user_text=user_text,
            ),
        )

    def rerun_current_workflow(
        self,
        *,
        session_id: str,
        uploaded_files: Sequence[Union[str, Path]],
        user_text: str,
    ) -> WorkflowResult:
        return self.run_current_workflow(
            session_id=session_id,
            workflow_inputs=self.build_runtime_inputs(
                session_id=session_id,
                uploaded_files=uploaded_files,
                user_text=user_text,
            ),
        )

    def present_result(self, result: WorkflowResult) -> RunPresentation:
        workflow = self.store.get_workflow_version(
            result.workflow_id,
            result.workflow_version,
        )
        titles = {
            step.id: ACTIVITY_LABELS.get(
                step.step_type,
                step.title or f"处理环节 {index}",
            )
            for index, step in enumerate(workflow.steps, start=1)
        }
        outputs = tuple(
            PresentedOutput(
                label=output.label or output.output_name,
                display_type=(
                    output.display_type.value
                    if output.display_type is not None
                    else output.value_type.value
                ),
                value=output.value,
            )
            for output in result.final_outputs
        )
        activities = tuple(
            ActivitySummary(
                title=titles.get(step_run.step_id, "处理环节"),
                status=step_run.status.value,
                error_message=step_run.error_message,
            )
            for step_run in result.step_runs
        )
        return RunPresentation(
            version=result.workflow_version,
            status=result.status.value,
            outputs=outputs,
            activities=activities,
            error_message=result.error_message,
        )

    def prepare_workflow(
        self,
        *,
        session_id: str,
        user_request: str,
        uploaded_files: Sequence[Union[str, Path]] = (),
    ) -> OrchestratorResponse:
        state = self._session_state(session_id)
        clarification = self.planner.clarify(user_request, uploaded_files)
        if clarification.unsupported:
            unsupported_state = self._transition(
                session_id, state, OrchestratorEvent.UNSUPPORTED_REQUEST
            )
            return self._clarification_response(
                session_id, unsupported_state, clarification
            )
        if clarification.needs_more_info:
            collecting_state = self._ensure_collecting_state(session_id, state)
            collecting_state = self._transition(
                session_id,
                collecting_state,
                OrchestratorEvent.NEEDS_MORE_INFO,
            )
            return self._clarification_response(
                session_id, collecting_state, clarification
            )

        collecting_state = self._ensure_collecting_state(session_id, state)
        plan = self.planner.create_workflow(user_request, uploaded_files)
        self.store.save_workflow_version(
            session_id=session_id,
            workflow=plan.workflow,
            plan_text=plan.plan_text,
            user_request=user_request,
        )
        awaiting_state = self._transition(
            session_id,
            collecting_state,
            OrchestratorEvent.WORKFLOW_READY,
        )
        return OrchestratorResponse(
            session_id=session_id,
            state=awaiting_state,
            plan=plan,
        )

    def prepare_new_request(
        self,
        *,
        session_id: str,
        user_request: str,
        uploaded_files: Sequence[Union[str, Path]] = (),
    ) -> OrchestratorResponse:
        state = self._session_state(session_id)
        if state in {OrchestratorState.COMPLETED, OrchestratorState.FAILED}:
            self._transition(
                session_id,
                state,
                OrchestratorEvent.USER_REQUESTED_NEW_WORKFLOW,
            )
        elif state not in {
            OrchestratorState.COLLECTING_REQUIREMENTS,
            OrchestratorState.UNSUPPORTED,
        }:
            raise ValueError(
                "当前已有待处理任务。请先完成当前操作，或开始新的会话。"
            )
        return self.prepare_workflow(
            session_id=session_id,
            user_request=user_request,
            uploaded_files=uploaded_files,
        )

    def accept_one_time_report(
        self,
        *,
        session_id: str,
        user_request: str,
        uploaded_files: Sequence[Union[str, Path]],
    ) -> OrchestratorResponse:
        state = self._session_state(session_id)
        collecting_state = self._transition(
            session_id,
            state,
            OrchestratorEvent.USER_REFRAMED_REQUEST,
        )
        plan = self.planner.create_workflow(
            user_request,
            uploaded_files,
            scenario=Scenario.ONE_TIME_REPORT,
        )
        self.store.save_workflow_version(
            session_id=session_id,
            workflow=plan.workflow,
            plan_text=plan.plan_text,
            user_request=user_request,
        )
        awaiting_state = self._transition(
            session_id,
            collecting_state,
            OrchestratorEvent.WORKFLOW_READY,
        )
        return OrchestratorResponse(
            session_id=session_id,
            state=awaiting_state,
            message=plan.limitation_message,
            plan=plan,
        )

    def revise_current_workflow(
        self,
        *,
        session_id: str,
        feedback: str,
    ) -> OrchestratorResponse:
        state = self._session_state(session_id)
        revising_state = self._transition(
            session_id,
            state,
            OrchestratorEvent.USER_REQUESTED_CHANGE,
        )
        current_workflow = self.store.get_current_workflow(session_id)
        plan = self.planner.revise_workflow(current_workflow, feedback)
        self.store.save_workflow_version(
            session_id=session_id,
            workflow=plan.workflow,
            plan_text=plan.plan_text,
            user_request=feedback,
        )
        awaiting_state = self._transition(
            session_id,
            revising_state,
            OrchestratorEvent.WORKFLOW_READY,
        )
        return OrchestratorResponse(
            session_id=session_id,
            state=awaiting_state,
            plan=plan,
        )

    def confirm_and_execute(
        self,
        *,
        session_id: str,
        workflow_inputs: Dict[str, Any],
    ) -> WorkflowResult:
        state = self._session_state(session_id)
        running_state = self._transition(
            session_id,
            state,
            OrchestratorEvent.USER_CONFIRMED,
        )
        return self._execute(session_id, workflow_inputs, running_state)

    def run_current_workflow(
        self,
        *,
        session_id: str,
        workflow_inputs: Dict[str, Any],
    ) -> WorkflowResult:
        state = self._session_state(session_id)
        if state == OrchestratorState.COMPLETED:
            event = OrchestratorEvent.USER_REQUESTED_NEW_RUN
        elif state == OrchestratorState.FAILED:
            event = OrchestratorEvent.USER_RETRY_REQUESTED
        elif state == OrchestratorState.AWAITING_CONFIRMATION:
            event = OrchestratorEvent.USER_CONFIRMED
        else:
            raise ValueError(
                f"Current workflow cannot run from state: {state.value}"
            )
        running_state = self._transition(session_id, state, event)
        return self._execute(session_id, workflow_inputs, running_state)

    def _execute(
        self,
        session_id: str,
        workflow_inputs: Dict[str, Any],
        running_state: OrchestratorState,
    ) -> WorkflowResult:
        if running_state != OrchestratorState.RUNNING:
            raise ValueError("Workflow execution requires RUNNING state.")
        workflow = self.store.get_current_workflow(session_id)
        run_id = self.store.create_run(
            session_id=session_id,
            workflow=workflow,
            workflow_inputs=workflow_inputs,
        )
        context = ExecutionContext(
            session_id=session_id,
            run_id=run_id,
            workflow_inputs=workflow_inputs,
        )
        result = execute_workflow(
            workflow,
            context,
            handler_map=self.handler_map,
            allowed_file_roots=self.file_store.allowed_source_roots,
        )
        self.store.save_run_result(result)
        event = (
            OrchestratorEvent.EXECUTION_SUCCEEDED
            if result.status == WorkflowStatus.COMPLETED
            else OrchestratorEvent.EXECUTION_FAILED
        )
        self._transition(session_id, running_state, event)
        return result

    def _clarification_response(
        self,
        session_id: str,
        state: OrchestratorState,
        clarification: Clarification,
    ) -> OrchestratorResponse:
        return OrchestratorResponse(
            session_id=session_id,
            state=state,
            message=clarification.message,
            questions=clarification.questions,
        )

    def _ensure_collecting_state(
        self,
        session_id: str,
        state: OrchestratorState,
    ) -> OrchestratorState:
        if state == OrchestratorState.COLLECTING_REQUIREMENTS:
            return state
        if state == OrchestratorState.UNSUPPORTED:
            return self._transition(
                session_id,
                state,
                OrchestratorEvent.USER_REFRAMED_REQUEST,
            )
        raise ValueError(f"Cannot prepare workflow from state: {state.value}")

    def _transition(
        self,
        session_id: str,
        state: OrchestratorState,
        event: OrchestratorEvent,
    ) -> OrchestratorState:
        next_state = transition_state(state, event)
        self.store.update_session_state(session_id, next_state)
        return next_state

    def _session_state(self, session_id: str) -> OrchestratorState:
        try:
            return OrchestratorState(self.store.get_session(session_id)["state"])
        except SQLiteStoreError:
            raise
