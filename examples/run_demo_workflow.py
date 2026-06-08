from __future__ import annotations

import json
from pathlib import Path

from config import PROJECT_ROOT
from core.executor import execute_workflow, validate_workflow
from core.workflow_schema import ExecutionContext, Workflow
from tools.documents import read_document
from tools.text_generation import generate_text


WORKFLOW_PATH = PROJECT_ROOT / "examples" / "demo_summary_workflow.json"
SAMPLE_PATH = PROJECT_ROOT / "examples" / "sample.txt"


def load_demo_workflow() -> Workflow:
    with WORKFLOW_PATH.open(encoding="utf-8") as workflow_file:
        return Workflow.model_validate(json.load(workflow_file))


def create_demo_context() -> ExecutionContext:
    return ExecutionContext(
        session_id="demo_session",
        run_id="demo_summary_run",
        workflow_inputs={"source_files": [str(SAMPLE_PATH)]},
    )


def run_demo() -> None:
    workflow = load_demo_workflow()
    context = create_demo_context()

    validation_status = validate_workflow(workflow, context)
    print(f"Validation: {validation_status.value}")

    result = execute_workflow(
        workflow,
        context,
        handler_map={
            "read_document": read_document,
            "generate_text": generate_text,
        },
    )

    print("WorkflowResult:")
    print(result.model_dump_json(indent=2))
    print("\nFinal summary:")
    print(context.step_outputs.get("generate_1", {}).get("text", "<not generated>"))


if __name__ == "__main__":
    run_demo()
