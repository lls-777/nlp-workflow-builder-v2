from __future__ import annotations

import inspect
from typing import Any, Iterator

import pytest

from core.executor import WorkflowValidationError, execute_workflow, validate_workflow
from core.logging_utils import LOG_FILE
from core.workflow_schema import StepStatus, Workflow, WorkflowStatus
from examples.run_data_analysis_workflow import HANDLER_MAP, create_context, load_workflow
from tools import data_analysis


def walk_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield str(key)
            yield from walk_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from walk_keys(nested_value)


def test_data_analysis_workflow_executes_successfully() -> None:
    workflow = load_workflow()
    context = create_context()

    assert validate_workflow(workflow, context) == WorkflowStatus.VALIDATED
    result = execute_workflow(workflow, context, handler_map=HANDLER_MAP)

    assert result.status == WorkflowStatus.COMPLETED
    assert [step.status for step in result.step_runs] == [
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
        StepStatus.COMPLETED,
    ]
    ranking = context.step_outputs["sort_sales_totals"]["table"]
    assert ranking["records"] == [
        {"region": "North", "total_sales": 2000},
        {"region": "East", "total_sales": 2000},
        {"region": "South", "total_sales": 1600},
    ]
    chart = context.step_outputs["build_sales_chart"]["chart"]
    assert chart["chart_type"] == "bar"
    assert chart["data"] == [
        {"region": "North", "total_sales": 2000},
        {"region": "East", "total_sales": 2000},
        {"region": "South", "total_sales": 1600},
    ]
    assert context.step_outputs["generate_sales_insights"]["text"].startswith(
        "Business insights:"
    )
    assert "/Users/" not in context.step_outputs["generate_sales_insights"]["text"]


@pytest.mark.parametrize(
    "field",
    ["code", "python", "eval", "exec", "query", "pandas_expression", "lambda", "python_code"],
)
def test_data_analysis_workflow_rejects_dynamic_expression_fields(field: str) -> None:
    payload = load_workflow().model_dump(mode="json")
    filter_step = next(step for step in payload["steps"] if step["id"] == "filter_completed_sales")
    filter_step["params"][field] = "unsafe"
    workflow = Workflow.model_validate(payload)

    with pytest.raises(WorkflowValidationError, match="Invalid params"):
        validate_workflow(workflow)


def test_data_analysis_tool_source_does_not_use_dynamic_execution() -> None:
    source = inspect.getsource(data_analysis)

    assert "eval(" not in source
    assert "exec(" not in source
    assert ".query(" not in source
    assert "lambda " not in source


def test_data_analysis_runtime_log_does_not_include_table_rows() -> None:
    workflow = load_workflow()
    context = create_context()

    result = execute_workflow(workflow, context, handler_map=HANDLER_MAP)

    assert result.status == WorkflowStatus.COMPLETED
    matching_lines = [
        line
        for line in LOG_FILE.read_text(encoding="utf-8").splitlines()
        if f"run_id={context.run_id}" in line
    ]
    assert matching_lines
    assert all("Starter" not in line for line in matching_lines)
    assert all("Premium" not in line for line in matching_lines)
    assert all("sales_amount" not in line for line in matching_lines)
