from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class FileRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    state: str


class UploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: List[FileRef]


class PrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_request: str = Field(min_length=1)
    files: List[FileRef] = Field(default_factory=list)


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_text: str = Field(min_length=1)
    files: List[FileRef] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback: str = Field(min_length=1)


class ActivityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    status: str
    error_message: Optional[str] = None


class OutputResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    display_type: str
    value: Any


class PrepareResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    state: str
    message: Optional[str] = None
    questions: List[str] = Field(default_factory=list)
    plan_text: Optional[str] = None
    limitation_message: Optional[str] = None
    debug: Dict[str, Any] = Field(default_factory=dict)


class RunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    run_id: str
    state: str
    status: str
    version: int
    outputs: List[OutputResponse] = Field(default_factory=list)
    activities: List[ActivityResponse] = Field(default_factory=list)
    error_message: Optional[str] = None
    debug: Dict[str, Any] = Field(default_factory=dict)
