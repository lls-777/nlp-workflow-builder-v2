from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from core.orchestrator import Orchestrator, OrchestratorResponse
from storage.sqlite_store import SQLiteStoreError

from .schemas import (
    ActivityResponse,
    ExecuteRequest,
    FeedbackRequest,
    FileRef,
    OutputResponse,
    PrepareRequest,
    PrepareResponse,
    RunResponse,
    SessionResponse,
    UploadResponse,
)

INTERNAL_VALUE_KEYS = {"path", "source_path"}


def create_app(orchestrator: Optional[Orchestrator] = None) -> FastAPI:
    active_orchestrator = orchestrator or Orchestrator()
    app = FastAPI(title="Natural Language Workflow Builder Hybrid API")
    app.state.orchestrator = active_orchestrator
    app.state.file_refs_by_session = {}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/sessions", response_model=SessionResponse)
    def create_session() -> SessionResponse:
        session = active_orchestrator.create_session()
        return SessionResponse(
            session_id=session["session_id"],
            state=session["state"],
        )

    @app.post("/api/sessions/{session_id}/uploads", response_model=UploadResponse)
    async def upload_files(
        session_id: str,
        files: List[UploadFile] = File(...),
    ) -> UploadResponse:
        _require_session(active_orchestrator, session_id)
        uploads = []
        for uploaded_file in files:
            content = await uploaded_file.read()
            uploads.append((uploaded_file.filename or "upload", content))
        existing_refs = _session_file_refs(app, session_id)
        try:
            stored_paths = active_orchestrator.save_uploads(
                uploads=uploads,
                existing_paths=[
                    active_orchestrator.file_store.uploads_dir / file_ref.id
                    for file_ref in existing_refs
                ],
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=_public_error(exc)) from exc
        new_refs = [
            FileRef(id=path.name, name=original_name)
            for path, (original_name, _) in zip(stored_paths, uploads)
        ]
        app.state.file_refs_by_session[session_id] = existing_refs + new_refs
        return UploadResponse(files=app.state.file_refs_by_session[session_id])

    @app.post("/api/sessions/{session_id}/prepare", response_model=PrepareResponse)
    def prepare_workflow(
        session_id: str,
        request_body: PrepareRequest,
    ) -> PrepareResponse:
        try:
            response = active_orchestrator.prepare_new_request(
                session_id=session_id,
                user_request=request_body.user_request,
                uploaded_files=_file_refs_to_paths(active_orchestrator, request_body.files, _session_file_ids(app, session_id)),
            )
        except (ValueError, SQLiteStoreError) as exc:
            raise HTTPException(status_code=400, detail=_public_error(exc)) from exc
        return _prepare_response(response)

    @app.post("/api/sessions/{session_id}/execute", response_model=RunResponse)
    def execute_workflow(
        session_id: str,
        request_body: ExecuteRequest,
    ) -> RunResponse:
        try:
            result = active_orchestrator.execute_prepared_workflow(
                session_id=session_id,
                uploaded_files=_file_refs_to_paths(active_orchestrator, request_body.files, _session_file_ids(app, session_id)),
                user_text=request_body.user_text,
            )
        except (ValueError, SQLiteStoreError) as exc:
            raise HTTPException(status_code=400, detail=_public_error(exc)) from exc
        return _run_response(active_orchestrator, session_id, result.run_id)

    @app.post("/api/sessions/{session_id}/feedback", response_model=PrepareResponse)
    def revise_workflow(
        session_id: str,
        request_body: FeedbackRequest,
    ) -> PrepareResponse:
        try:
            response = active_orchestrator.revise_current_workflow(
                session_id=session_id,
                feedback=request_body.feedback,
            )
        except (ValueError, SQLiteStoreError) as exc:
            raise HTTPException(status_code=400, detail=_public_error(exc)) from exc
        return _prepare_response(response)

    @app.post("/api/sessions/{session_id}/follow-up", response_model=RunResponse)
    def follow_up(
        session_id: str,
        request_body: ExecuteRequest,
    ) -> RunResponse:
        try:
            result = active_orchestrator.rerun_current_workflow(
                session_id=session_id,
                uploaded_files=_file_refs_to_paths(active_orchestrator, request_body.files, _session_file_ids(app, session_id)),
                user_text=request_body.user_text,
            )
        except (ValueError, SQLiteStoreError) as exc:
            raise HTTPException(status_code=400, detail=_public_error(exc)) from exc
        return _run_response(active_orchestrator, session_id, result.run_id)

    @app.get("/api/sessions/{session_id}/runs/{run_id}", response_model=RunResponse)
    def get_run(session_id: str, run_id: str) -> RunResponse:
        _require_session(active_orchestrator, session_id)
        return _run_response(active_orchestrator, session_id, run_id)

    return app


def _require_session(orchestrator: Orchestrator, session_id: str) -> None:
    try:
        orchestrator.store.get_session(session_id)
    except SQLiteStoreError as exc:
        raise HTTPException(status_code=404, detail="Session does not exist.") from exc


def _session_file_refs(app: FastAPI, session_id: str) -> List[FileRef]:
    return list(app.state.file_refs_by_session.get(session_id, []))


def _session_file_ids(app: FastAPI, session_id: str) -> Sequence[str]:
    return [file_ref.id for file_ref in _session_file_refs(app, session_id)]


def _file_refs_to_paths(
    orchestrator: Orchestrator,
    files: Sequence[FileRef],
    allowed_file_ids: Sequence[str],
) -> List[Path]:
    allowed_ids = set(allowed_file_ids)
    paths = []
    for file_ref in files:
        if "/" in file_ref.id or "\\" in file_ref.id or file_ref.id in {".", ".."}:
            raise ValueError("Invalid uploaded file reference.")
        if file_ref.id not in allowed_ids:
            raise ValueError("Uploaded file reference does not belong to this session.")
        paths.append(
            orchestrator.file_store.resolve_upload(
                orchestrator.file_store.uploads_dir / file_ref.id
            )
        )
    return list(paths)


def _prepare_response(response: OrchestratorResponse) -> PrepareResponse:
    workflow = response.plan.workflow if response.plan is not None else None
    return PrepareResponse(
        session_id=response.session_id,
        state=response.state.value,
        message=response.message,
        questions=list(response.questions),
        plan_text=response.plan.plan_text if response.plan is not None else None,
        limitation_message=(
            response.plan.limitation_message if response.plan is not None else None
        ),
        debug={
            "scenario": response.plan.scenario.value if response.plan is not None else None,
            "workflow": workflow.model_dump(mode="json") if workflow is not None else None,
        },
    )


def _run_response(orchestrator: Orchestrator, session_id: str, run_id: str) -> RunResponse:
    run = orchestrator.store.get_run(run_id)
    if run["session_id"] != session_id:
        raise HTTPException(status_code=404, detail="Run does not exist for this session.")
    result_json = run.get("result_json")
    if not isinstance(result_json, Mapping):
        raise HTTPException(status_code=404, detail="Run has no result yet.")
    workflow_id = str(run["workflow_id"])
    workflow_version = int(run["workflow_version"])
    workflow = orchestrator.store.get_workflow_version(workflow_id, workflow_version)
    from core.workflow_schema import WorkflowResult

    result = WorkflowResult.model_validate(result_json)
    presentation = orchestrator.present_result(result)
    state = orchestrator.store.get_session(session_id)["state"]
    return RunResponse(
        session_id=session_id,
        run_id=run_id,
        state=state,
        status=presentation.status,
        version=presentation.version,
        outputs=[
            OutputResponse(
                label=output.label,
                display_type=output.display_type,
                value=_public_value(output.value),
            )
            for output in presentation.outputs
        ],
        activities=[
            ActivityResponse(
                title=activity.title,
                status=activity.status,
                error_message=(
                    _public_error(activity.error_message)
                    if activity.error_message is not None
                    else None
                ),
            )
            for activity in presentation.activities
        ],
        error_message=(
            _public_error(presentation.error_message)
            if presentation.error_message is not None
            else None
        ),
        debug={
            "workflow_id": workflow.id,
            "workflow_version": workflow.version,
            "workflow": workflow.model_dump(mode="json"),
        },
    )


def _public_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _public_value(item)
            for key, item in value.items()
            if str(key) not in INTERNAL_VALUE_KEYS
        }
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    return value


def _public_error(error: Any) -> str:
    message = str(error or "").strip()
    if not message:
        return "处理失败，请检查输入后重试。"
    return message.replace(str(Path.home()), "~")


app = create_app()
