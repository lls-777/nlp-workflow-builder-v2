from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from config import PROJECT_ROOT
from core.executor import execute_workflow, validate_workflow
from core.workflow_schema import ExecutionContext, Workflow
from tools.documents import read_document
from tools.qa import answer_with_sources
from tools.retrieval import chunk_document, retrieve_chunks


WORKFLOW_DIR = PROJECT_ROOT / "examples" / "workflows"
SAMPLE_FAQ_PATH = PROJECT_ROOT / "examples" / "sample_faq.md"
HANDLER_MAP = {
    "read_document": read_document,
    "chunk_document": chunk_document,
    "retrieve_chunks": retrieve_chunks,
    "answer_with_sources": answer_with_sources,
}


def load_workflow(file_name: str) -> Workflow:
    with (WORKFLOW_DIR / file_name).open(encoding="utf-8") as workflow_file:
        return Workflow.model_validate(json.load(workflow_file))


def create_context(*, run_id: str, question: str) -> ExecutionContext:
    return ExecutionContext(
        session_id="document_qa_demo_session",
        run_id=run_id,
        workflow_inputs={
            "source_files": [str(SAMPLE_FAQ_PATH)],
            "question": question,
        },
    )


def run_workflow(file_name: str, *, run_id: str, question: str) -> Dict[str, object]:
    workflow = load_workflow(file_name)
    context = create_context(run_id=run_id, question=question)
    validation_status = validate_workflow(workflow, context)
    print(f"{file_name} validation: {validation_status.value}")

    result = execute_workflow(workflow, context, handler_map=HANDLER_MAP)
    answer_step_id = workflow.steps[-1].id
    outputs = context.step_outputs.get(answer_step_id, {})
    print(f"{file_name} status: {result.status.value}")
    print(f"{file_name} answer:\n{outputs.get('text', '<not generated>')}")
    print(f"{file_name} citations:")
    print(json.dumps(outputs.get("citations", []), ensure_ascii=False, indent=2))
    return outputs


def run_demo() -> None:
    run_workflow(
        "document_qa.json",
        run_id="document_qa_demo_run",
        question="What information is required for a member refund request?",
    )
    print()
    run_workflow(
        "faq_customer_service.json",
        run_id="faq_customer_service_demo_run",
        question="Can a member request a refund?",
    )
    print()
    run_workflow(
        "document_qa.json",
        run_id="document_qa_refusal_demo_run",
        question="What is the office parking policy?",
    )


if __name__ == "__main__":
    run_demo()
