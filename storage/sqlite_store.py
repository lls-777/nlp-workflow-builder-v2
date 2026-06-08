from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from config import DATA_DIR
from core.orchestrator_state import OrchestratorState
from core.workflow_schema import StepRunResult, Workflow, WorkflowResult, WorkflowStatus


DEFAULT_DATABASE_PATH = DATA_DIR / "app.db"


class SQLiteStoreError(ValueError):
    """Raised when local persistence cannot complete an operation."""


class SQLiteStore:
    def __init__(self, database_path: Union[str, Path] = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def create_session(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        now = _utc_now()
        resolved_session_id = session_id or f"session_{uuid4().hex}"
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO sessions (
                        session_id, state, current_workflow_id,
                        current_workflow_version, created_at, updated_at
                    ) VALUES (?, ?, NULL, NULL, ?, ?)
                    """,
                    (
                        resolved_session_id,
                        OrchestratorState.COLLECTING_REQUIREMENTS.value,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise SQLiteStoreError(
                    f"Session already exists: {resolved_session_id}"
                ) from exc
        return self.get_session(resolved_session_id)

    def get_session(self, session_id: str) -> Dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise SQLiteStoreError(f"Session does not exist: {session_id}")
        return dict(row)

    def update_session_state(
        self,
        session_id: str,
        state: OrchestratorState,
    ) -> Dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE sessions SET state = ?, updated_at = ? WHERE session_id = ?",
                (state.value, _utc_now(), session_id),
            )
        if cursor.rowcount != 1:
            raise SQLiteStoreError(f"Session does not exist: {session_id}")
        return self.get_session(session_id)

    def save_workflow_version(
        self,
        *,
        session_id: str,
        workflow: Workflow,
        plan_text: str,
        user_request: str,
    ) -> Workflow:
        now = _utc_now()
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO workflow_versions (
                        workflow_id, version, session_id, workflow_json,
                        plan_text, user_request, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workflow.id,
                        workflow.version,
                        session_id,
                        workflow.model_dump_json(),
                        plan_text,
                        user_request,
                        now,
                    ),
                )
                connection.execute(
                    """
                    UPDATE sessions
                    SET current_workflow_id = ?, current_workflow_version = ?,
                        updated_at = ?
                    WHERE session_id = ?
                    """,
                    (workflow.id, workflow.version, now, session_id),
                )
            except sqlite3.IntegrityError as exc:
                raise SQLiteStoreError(
                    f"Workflow version already exists: {workflow.id} v{workflow.version}"
                ) from exc
        return workflow

    def get_workflow_version(
        self,
        workflow_id: str,
        version: Optional[int] = None,
    ) -> Workflow:
        with self._connect() as connection:
            if version is None:
                row = connection.execute(
                    """
                    SELECT workflow_json FROM workflow_versions
                    WHERE workflow_id = ?
                    ORDER BY version DESC LIMIT 1
                    """,
                    (workflow_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT workflow_json FROM workflow_versions
                    WHERE workflow_id = ? AND version = ?
                    """,
                    (workflow_id, version),
                ).fetchone()
        if row is None:
            suffix = "" if version is None else f" v{version}"
            raise SQLiteStoreError(f"Workflow version does not exist: {workflow_id}{suffix}")
        return Workflow.model_validate_json(row["workflow_json"])

    def get_current_workflow(self, session_id: str) -> Workflow:
        session = self.get_session(session_id)
        workflow_id = session["current_workflow_id"]
        version = session["current_workflow_version"]
        if workflow_id is None or version is None:
            raise SQLiteStoreError(f"Session has no workflow: {session_id}")
        return self.get_workflow_version(workflow_id, int(version))

    def list_workflow_versions(self, session_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT workflow_id, version, session_id, plan_text,
                       user_request, created_at
                FROM workflow_versions
                WHERE session_id = ?
                ORDER BY created_at, version
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_run(
        self,
        *,
        session_id: str,
        workflow: Workflow,
        workflow_inputs: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> str:
        resolved_run_id = run_id or f"run_{uuid4().hex}"
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO runs (
                        run_id, session_id, workflow_id, workflow_version,
                        status, inputs_json, result_json, error_message,
                        created_at, finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL)
                    """,
                    (
                        resolved_run_id,
                        session_id,
                        workflow.id,
                        workflow.version,
                        WorkflowStatus.PENDING.value,
                        _json_dump(workflow_inputs),
                        _utc_now(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise SQLiteStoreError(f"Run already exists: {resolved_run_id}") from exc
        return resolved_run_id

    def save_run_result(self, result: WorkflowResult) -> WorkflowResult:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runs
                SET status = ?, result_json = ?, error_message = ?, finished_at = ?
                WHERE run_id = ?
                """,
                (
                    result.status.value,
                    result.model_dump_json(),
                    result.error_message,
                    _utc_now(),
                    result.run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise SQLiteStoreError(f"Run does not exist: {result.run_id}")
            connection.execute("DELETE FROM step_runs WHERE run_id = ?", (result.run_id,))
            for step_run in result.step_runs:
                self._insert_step_run(connection, result.run_id, step_run)
        return result

    def get_run(self, run_id: str) -> Dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise SQLiteStoreError(f"Run does not exist: {run_id}")
        return _decode_json_fields(dict(row), "inputs_json", "result_json")

    def list_runs(self, session_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM runs WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ).fetchall()
        return [
            _decode_json_fields(dict(row), "inputs_json", "result_json")
            for row in rows
        ]

    def list_step_runs(self, run_id: str) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM step_runs
                WHERE run_id = ?
                ORDER BY sequence_number
                """,
                (run_id,),
            ).fetchall()
        return [
            _decode_json_fields(dict(row), "outputs_json")
            for row in rows
        ]

    def list_tables(self) -> List[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        return [str(row["name"]) for row in rows]

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    current_workflow_id TEXT,
                    current_workflow_version INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workflow_versions (
                    workflow_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    workflow_json TEXT NOT NULL,
                    plan_text TEXT NOT NULL,
                    user_request TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (workflow_id, version),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    workflow_version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    inputs_json TEXT NOT NULL,
                    result_json TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
                    FOREIGN KEY (workflow_id, workflow_version)
                        REFERENCES workflow_versions(workflow_id, version)
                );

                CREATE TABLE IF NOT EXISTS step_runs (
                    run_id TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    step_id TEXT NOT NULL,
                    step_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    outputs_json TEXT NOT NULL,
                    preview TEXT,
                    error_message TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    PRIMARY KEY (run_id, sequence_number),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _insert_step_run(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        step_run: StepRunResult,
    ) -> None:
        sequence_number = connection.execute(
            "SELECT COUNT(*) AS count FROM step_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()["count"]
        connection.execute(
            """
            INSERT INTO step_runs (
                run_id, sequence_number, step_id, step_type, status,
                outputs_json, preview, error_message, started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                sequence_number,
                step_run.step_id,
                step_run.step_type,
                step_run.status.value,
                _json_dump(
                    [output.model_dump(mode="json") for output in step_run.outputs]
                ),
                step_run.preview,
                step_run.error_message,
                _datetime_text(step_run.started_at),
                _datetime_text(step_run.finished_at),
            ),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _datetime_text(value: Optional[datetime]) -> Optional[str]:
    return None if value is None else value.isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        sort_keys=True,
    )


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Value is not JSON serializable: {type(value).__name__}")


def _decode_json_fields(record: Dict[str, Any], *fields: str) -> Dict[str, Any]:
    for field in fields:
        if record.get(field) is not None:
            record[field] = json.loads(record[field])
    return record
