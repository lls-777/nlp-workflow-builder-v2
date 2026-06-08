from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional, Union

from config import PROJECT_ROOT
from core.workflow_schema import StepStatus, WorkflowStatus


LOG_FILE = PROJECT_ROOT / "logs" / "app.log"
LOGGER_NAME = "project_nlp.runtime"
MAX_LOG_FIELD_LENGTH = 240

_SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*\S+"
)


def _safe_field(value: object) -> str:
    normalized = " ".join(str(value).split())
    redacted = _SENSITIVE_VALUE_PATTERN.sub(r"\1=[REDACTED]", normalized)
    if len(redacted) <= MAX_LOG_FIELD_LENGTH:
        return redacted
    return f"{redacted[: MAX_LOG_FIELD_LENGTH - 3]}..."


def get_runtime_logger(
    *,
    log_file: Path = LOG_FILE,
    logger_name: str = LOGGER_NAME,
) -> logging.Logger:
    logger = logging.getLogger(logger_name)
    if getattr(logger, "_project_nlp_configured", False):
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    setattr(logger, "_project_nlp_configured", True)
    return logger


def log_workflow_status(
    *,
    workflow_id: str,
    run_id: str,
    status: WorkflowStatus,
    error_summary: Optional[Union[str, Exception]] = None,
) -> None:
    fields = [
        f"workflow_id={_safe_field(workflow_id)}",
        f"run_id={_safe_field(run_id)}",
        f"status={status.value}",
    ]
    if error_summary is not None:
        fields.append(f"error_summary={_safe_field(error_summary)}")
    get_runtime_logger().info("workflow %s", " ".join(fields))


def log_step_status(
    *,
    workflow_id: str,
    run_id: str,
    step_id: str,
    step_type: str,
    status: StepStatus,
    error_summary: Optional[Union[str, Exception]] = None,
) -> None:
    fields = [
        f"workflow_id={_safe_field(workflow_id)}",
        f"run_id={_safe_field(run_id)}",
        f"step_id={_safe_field(step_id)}",
        f"step_type={_safe_field(step_type)}",
        f"status={status.value}",
    ]
    if error_summary is not None:
        fields.append(f"error_summary={_safe_field(error_summary)}")
    get_runtime_logger().info("step %s", " ".join(fields))
