from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourcePolicy(str, Enum):
    UPLOADED_FILES_ONLY = "uploaded_files_only"
    USER_PROVIDED_ONLY = "user_provided_only"
    NETWORK_ALLOWED = "network_allowed"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BindingSource(str, Enum):
    WORKFLOW_INPUT = "workflow_input"
    STEP_OUTPUT = "step_output"


class ValueType(str, Enum):
    FILE = "file"
    FILES = "files"
    TEXT = "text"
    DOCUMENTS = "documents"
    CHUNKS = "chunks"
    RETRIEVED_CHUNKS = "retrieved_chunks"
    TABLE = "table"
    TABLE_PROFILE = "table_profile"
    CHART = "chart"
    CITATIONS = "citations"
    ARTIFACT = "artifact"


class DisplayType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    CITATIONS = "citations"
    ARTIFACT = "artifact"


class WorkflowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value_type: ValueType
    required: bool = True


class InputBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: BindingSource
    input_name: Optional[str] = None
    step_id: Optional[str] = None
    output_name: Optional[str] = None

    @model_validator(mode="after")
    def validate_source_fields(self) -> "InputBinding":
        if self.source == BindingSource.WORKFLOW_INPUT:
            if not self.input_name:
                raise ValueError("workflow_input binding requires input_name")
            if self.step_id is not None or self.output_name is not None:
                raise ValueError(
                    "workflow_input binding cannot define step_id or output_name"
                )
            return self

        if not self.step_id or not self.output_name:
            raise ValueError("step_output binding requires step_id and output_name")
        if self.input_name is not None:
            raise ValueError("step_output binding cannot define input_name")
        return self


class StepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    bindings: List[InputBinding] = Field(min_length=1)


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    step_type: str = Field(min_length=1)
    inputs: List[StepInput] = Field(default_factory=list)
    params: Dict[str, Any] = Field(default_factory=dict)
    title: Optional[str] = None


class ResultBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    output_name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    display_type: DisplayType


class StepOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_name: str = Field(min_length=1)
    value_type: ValueType
    label: Optional[str] = None
    display_type: Optional[DisplayType] = None
    value: Optional[Any] = None
    persistent_ref: Optional[str] = None
    preview: Optional[str] = None
    artifact_id: Optional[str] = None


class ExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    session_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    workflow_inputs: Dict[str, Any] = Field(default_factory=dict)
    step_outputs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class StepRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    step_type: str = Field(min_length=1)
    status: StepStatus
    outputs: List[StepOutput] = Field(default_factory=list)
    preview: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class WorkflowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1)
    workflow_version: int = Field(ge=1)
    run_id: str = Field(min_length=1)
    status: WorkflowStatus
    step_runs: List[StepRunResult] = Field(default_factory=list)
    final_outputs: List[StepOutput] = Field(default_factory=list)
    error_message: Optional[str] = None


class Workflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    goal: str = Field(min_length=1)
    source_policy: SourcePolicy
    workflow_inputs: List[WorkflowInput] = Field(default_factory=list)
    steps: List[Step] = Field(min_length=1)
    result_bindings: List[ResultBinding] = Field(min_length=1)
