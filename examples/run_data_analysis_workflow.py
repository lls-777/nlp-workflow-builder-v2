from __future__ import annotations

import json

from config import PROJECT_ROOT
from core.executor import execute_workflow, validate_workflow
from core.workflow_schema import ExecutionContext, Workflow
from tools.data_analysis import (
    aggregate_table,
    filter_table,
    profile_table,
    read_table,
    render_chart,
    sort_table,
)
from tools.text_generation import generate_text


WORKFLOW_PATH = PROJECT_ROOT / "examples" / "workflows" / "data_analysis.json"
SAMPLE_SALES_PATH = PROJECT_ROOT / "examples" / "sample_sales.csv"
HANDLER_MAP = {
    "read_table": read_table,
    "profile_table": profile_table,
    "filter_table": filter_table,
    "aggregate_table": aggregate_table,
    "sort_table": sort_table,
    "render_chart": render_chart,
    "generate_text": generate_text,
}


def load_workflow() -> Workflow:
    with WORKFLOW_PATH.open(encoding="utf-8") as workflow_file:
        return Workflow.model_validate(json.load(workflow_file))


def create_context() -> ExecutionContext:
    return ExecutionContext(
        session_id="data_analysis_demo_session",
        run_id="data_analysis_demo_run",
        workflow_inputs={"source_file": str(SAMPLE_SALES_PATH)},
    )


def run_demo() -> None:
    workflow = load_workflow()
    context = create_context()
    validation_status = validate_workflow(workflow, context)
    print(f"Validation: {validation_status.value}")

    result = execute_workflow(workflow, context, handler_map=HANDLER_MAP)
    print(f"Workflow status: {result.status.value}")
    print("Regional sales ranking:")
    print(json.dumps(
        context.step_outputs.get("sort_sales_totals", {}).get("table", {}),
        ensure_ascii=False,
        indent=2,
    ))
    print("Chart specification:")
    print(json.dumps(
        context.step_outputs.get("build_sales_chart", {}).get("chart", {}),
        ensure_ascii=False,
        indent=2,
    ))
    print("Business insights:")
    print(
        context.step_outputs.get("generate_sales_insights", {}).get(
            "text", "<not generated>"
        )
    )


if __name__ == "__main__":
    run_demo()
