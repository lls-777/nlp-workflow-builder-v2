from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple, Type

from pydantic import BaseModel, ConfigDict, Field, model_validator

from config import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MIN_RETRIEVAL_SCORE,
    DEFAULT_RETRIEVAL_TOP_K,
)
from core.workflow_schema import ValueType


class EmptyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChunkDocumentParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_size: int = Field(default=DEFAULT_CHUNK_SIZE, ge=1)
    overlap: int = Field(default=DEFAULT_CHUNK_OVERLAP, ge=0)

    @model_validator(mode="after")
    def validate_overlap(self) -> "ChunkDocumentParams":
        if self.overlap >= self.chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        return self


class RetrieveChunksParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(default=DEFAULT_RETRIEVAL_TOP_K, ge=1, le=50)


class GenerateTextParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: Literal["summary", "report", "business_insights"]
    bullet_count: Optional[int] = Field(default=None, ge=1, le=50)
    max_length: Optional[int] = Field(default=None, ge=1)


class AnswerWithSourcesParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_score: float = Field(default=DEFAULT_MIN_RETRIEVAL_SCORE, ge=0.0, le=1.0)


class ReadTableParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet_name: Optional[str] = None


class FilterCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1)
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"]
    value: Any


class FilterTableParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filters: List[FilterCondition] = Field(min_length=1)


class AggregationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: Optional[str] = None
    operation: Literal["count", "sum", "mean", "min", "max"]
    alias: Optional[str] = None

    @model_validator(mode="after")
    def validate_field(self) -> "AggregationSpec":
        if self.operation != "count" and not self.field:
            raise ValueError(f"{self.operation} aggregation requires field")
        return self


class AggregateTableParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_by: List[str] = Field(default_factory=list)
    aggregations: List[AggregationSpec] = Field(min_length=1)


class SortSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1)
    ascending: bool = True


class SortTableParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sort_by: List[SortSpec] = Field(min_length=1)


class RenderChartParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_type: Literal["bar", "line"]
    x: str = Field(min_length=1)
    y: str = Field(min_length=1)
    title: Optional[str] = None


class WebSearchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(default=DEFAULT_RETRIEVAL_TOP_K, ge=1, le=20)


@dataclass(frozen=True)
class InputPortSpec:
    allowed_value_types: Tuple[ValueType, ...]
    required: bool = True
    allow_multiple_bindings: bool = False


@dataclass(frozen=True)
class StepDefinition:
    step_type: str
    input_ports: Dict[str, InputPortSpec]
    output_ports: Dict[str, ValueType]
    params_model: Type[BaseModel]
    handler_name: str
    enabled: bool = True
    requires_network: bool = False


class StepRegistry:
    def __init__(self, definitions: Iterable[StepDefinition]) -> None:
        self._definitions = {
            definition.step_type: definition for definition in definitions
        }

    def get(self, step_type: str) -> Optional[StepDefinition]:
        return self._definitions.get(step_type)

    def planning_definitions(self) -> List[StepDefinition]:
        return [
            definition
            for definition in self._definitions.values()
            if definition.enabled
        ]

    def clone_with(self, step_type: str, **changes: Any) -> "StepRegistry":
        if step_type not in self._definitions:
            raise KeyError(step_type)
        definitions = dict(self._definitions)
        definitions[step_type] = replace(definitions[step_type], **changes)
        return StepRegistry(definitions.values())


STEP_REGISTRY = StepRegistry(
    [
        StepDefinition(
            step_type="read_document",
            input_ports={"files": InputPortSpec((ValueType.FILES,))},
            output_ports={"documents": ValueType.DOCUMENTS},
            params_model=EmptyParams,
            handler_name="read_document",
        ),
        StepDefinition(
            step_type="chunk_document",
            input_ports={"documents": InputPortSpec((ValueType.DOCUMENTS,))},
            output_ports={"chunks": ValueType.CHUNKS},
            params_model=ChunkDocumentParams,
            handler_name="chunk_document",
        ),
        StepDefinition(
            step_type="retrieve_chunks",
            input_ports={
                "chunks": InputPortSpec((ValueType.CHUNKS,)),
                "query": InputPortSpec((ValueType.TEXT,)),
            },
            output_ports={"retrieved_chunks": ValueType.RETRIEVED_CHUNKS},
            params_model=RetrieveChunksParams,
            handler_name="retrieve_chunks",
        ),
        StepDefinition(
            step_type="read_table",
            input_ports={"file": InputPortSpec((ValueType.FILE,))},
            output_ports={"table": ValueType.TABLE},
            params_model=ReadTableParams,
            handler_name="read_table",
        ),
        StepDefinition(
            step_type="profile_table",
            input_ports={"table": InputPortSpec((ValueType.TABLE,))},
            output_ports={"table_profile": ValueType.TABLE_PROFILE},
            params_model=EmptyParams,
            handler_name="profile_table",
        ),
        StepDefinition(
            step_type="filter_table",
            input_ports={"table": InputPortSpec((ValueType.TABLE,))},
            output_ports={"table": ValueType.TABLE},
            params_model=FilterTableParams,
            handler_name="filter_table",
        ),
        StepDefinition(
            step_type="aggregate_table",
            input_ports={"table": InputPortSpec((ValueType.TABLE,))},
            output_ports={"table": ValueType.TABLE},
            params_model=AggregateTableParams,
            handler_name="aggregate_table",
        ),
        StepDefinition(
            step_type="sort_table",
            input_ports={"table": InputPortSpec((ValueType.TABLE,))},
            output_ports={"table": ValueType.TABLE},
            params_model=SortTableParams,
            handler_name="sort_table",
        ),
        StepDefinition(
            step_type="render_chart",
            input_ports={"table": InputPortSpec((ValueType.TABLE,))},
            output_ports={"chart": ValueType.CHART},
            params_model=RenderChartParams,
            handler_name="render_chart",
        ),
        StepDefinition(
            step_type="generate_text",
            input_ports={
                "materials": InputPortSpec(
                    (
                        ValueType.DOCUMENTS,
                        ValueType.RETRIEVED_CHUNKS,
                        ValueType.TABLE,
                        ValueType.TABLE_PROFILE,
                        ValueType.TEXT,
                    ),
                    allow_multiple_bindings=True,
                )
            },
            output_ports={"text": ValueType.TEXT},
            params_model=GenerateTextParams,
            handler_name="generate_text",
        ),
        StepDefinition(
            step_type="answer_with_sources",
            input_ports={
                "retrieved_chunks": InputPortSpec((ValueType.RETRIEVED_CHUNKS,)),
                "question": InputPortSpec((ValueType.TEXT,)),
            },
            output_ports={
                "text": ValueType.TEXT,
                "citations": ValueType.CITATIONS,
            },
            params_model=AnswerWithSourcesParams,
            handler_name="answer_with_sources",
        ),
        StepDefinition(
            step_type="web_search",
            input_ports={"query": InputPortSpec((ValueType.TEXT,))},
            output_ports={"retrieved_chunks": ValueType.RETRIEVED_CHUNKS},
            params_model=WebSearchParams,
            handler_name="web_search",
            enabled=False,
            requires_network=True,
        ),
        StepDefinition(
            step_type="merge_sources",
            input_ports={
                "materials": InputPortSpec(
                    (ValueType.DOCUMENTS, ValueType.RETRIEVED_CHUNKS),
                    allow_multiple_bindings=True,
                )
            },
            output_ports={"documents": ValueType.DOCUMENTS},
            params_model=EmptyParams,
            handler_name="merge_sources",
            enabled=False,
        ),
    ]
)
