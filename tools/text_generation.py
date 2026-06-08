from __future__ import annotations

from typing import Any, Dict

from core.llm import get_llm_client
from core.workflow_schema import ExecutionContext


def generate_text(
    inputs: Dict[str, Any],
    params: Dict[str, Any],
    context: ExecutionContext,
) -> Dict[str, Any]:
    if "materials" not in inputs:
        raise ValueError("generate_text requires materials.")

    client = get_llm_client()
    text = client.generate_text(
        task=params["task"],
        materials=inputs["materials"],
        bullet_count=params.get("bullet_count"),
        max_length=params.get("max_length"),
    )
    return {"text": text}
