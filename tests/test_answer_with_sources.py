from __future__ import annotations

import json
from typing import Any, Dict

import pytest

from core import llm
from core.llm import CompatibleLLMClient, LLMError, LLMSettings
from tools.qa import REFUSAL_TEXT, answer_question_with_sources


def supporting_chunk(*, score: float = 0.8) -> Dict[str, Any]:
    return {
        "chunk_id": "faq.md::chunk_0001",
        "source_name": "faq.md",
        "source_path": "/private/internal/faq.md",
        "content": "Members can request a refund within 14 days of purchase.",
        "score": score,
    }


@pytest.mark.parametrize(
    "retrieved_chunks",
    [
        [],
        [supporting_chunk(score=0.05)],
    ],
)
def test_answer_refuses_when_evidence_is_missing_or_insufficient(
    retrieved_chunks: list,
) -> None:
    result = answer_question_with_sources(
        retrieved_chunks=retrieved_chunks,
        question="Can a member request a refund?",
        min_score=0.1,
    )

    assert result == {"text": REFUSAL_TEXT, "citations": []}


def test_answer_uses_retrieved_chunk_and_returns_safe_citation() -> None:
    result = answer_question_with_sources(
        retrieved_chunks=[supporting_chunk()],
        question="Can a member request a refund?",
        min_score=0.1,
    )

    assert "within 14 days" in result["text"]
    assert result["citations"] == [
        {
            "source_name": "faq.md",
            "excerpt": "Members can request a refund within 14 days of purchase.",
            "score": 0.8,
        }
    ]
    assert "source_path" not in result["citations"][0]
    assert "chunk_id" not in result["citations"][0]


def test_compatible_mode_requires_configuration() -> None:
    with pytest.raises(LLMError, match="LLM_API_KEY, LLM_BASE_URL, LLM_MODEL"):
        CompatibleLLMClient(LLMSettings(mode="compatible"))


def test_compatible_mode_uses_http_mock_without_external_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: Dict[str, Any] = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "Answer from the configured compatible service."
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(api_request: Any, timeout: int) -> FakeResponse:
        captured["url"] = api_request.full_url
        captured["authorization"] = api_request.headers["Authorization"]
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(llm.request, "urlopen", fake_urlopen)
    client = CompatibleLLMClient(
        LLMSettings(
            mode="compatible",
            api_key="test-key",
            base_url="https://compatible.example/v1",
            model="test-model",
        )
    )

    answer = client.answer_with_sources(
        question="Can a member request a refund?",
        retrieved_chunks=[supporting_chunk()],
    )

    assert answer == "Answer from the configured compatible service."
    assert captured == {
        "url": "https://compatible.example/v1/chat/completions",
        "authorization": "Bearer test-key",
        "timeout": 30,
    }
