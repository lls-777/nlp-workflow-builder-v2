from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from config import MAX_CITATION_EXCERPT_CHARS
from core.llm import get_llm_client
from core.workflow_schema import ExecutionContext


REFUSAL_TEXT = (
    "I cannot answer from the provided files because there is not enough "
    "supporting evidence."
)


def answer_question_with_sources(
    *,
    retrieved_chunks: Sequence[Mapping[str, Any]],
    question: str,
    min_score: float,
) -> Dict[str, Any]:
    normalized_question = question.strip() if isinstance(question, str) else ""
    relevant_chunks = [
        chunk
        for chunk in retrieved_chunks
        if str(chunk.get("content", "")).strip()
        and float(chunk.get("score", 0.0)) >= min_score
    ]
    if not normalized_question or not relevant_chunks:
        return {"text": REFUSAL_TEXT, "citations": []}

    text = get_llm_client().answer_with_sources(
        question=normalized_question,
        retrieved_chunks=relevant_chunks,
    )
    return {
        "text": text,
        "citations": [_build_citation(chunk) for chunk in relevant_chunks],
    }


def _build_citation(chunk: Mapping[str, Any]) -> Dict[str, Any]:
    normalized_excerpt = " ".join(str(chunk.get("content", "")).split())
    if len(normalized_excerpt) > MAX_CITATION_EXCERPT_CHARS:
        normalized_excerpt = f"{normalized_excerpt[: MAX_CITATION_EXCERPT_CHARS - 3]}..."
    return {
        "source_name": str(chunk.get("source_name", "")),
        "excerpt": normalized_excerpt,
        "score": round(float(chunk.get("score", 0.0)), 6),
    }


def answer_with_sources(
    inputs: Dict[str, Any],
    params: Dict[str, Any],
    context: ExecutionContext,
) -> Dict[str, Any]:
    retrieved_chunks = inputs.get("retrieved_chunks")
    if isinstance(retrieved_chunks, (str, bytes)) or not isinstance(
        retrieved_chunks, Sequence
    ):
        retrieved_chunks = []
    return answer_question_with_sources(
        retrieved_chunks=retrieved_chunks,
        question=inputs.get("question", ""),
        min_score=params["min_score"],
    )
