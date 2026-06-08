from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union
from urllib import error, request

from config import LLM_REQUEST_TIMEOUT_SECONDS


class LLMError(ValueError):
    """Raised when text generation cannot be completed."""


@dataclass(frozen=True)
class LLMSettings:
    mode: str = "mock"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None

    @classmethod
    def from_environment(cls) -> "LLMSettings":
        return cls(
            mode=os.getenv("LLM_MODE", "mock").strip().lower(),
            api_key=os.getenv("LLM_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL"),
            model=os.getenv("LLM_MODEL"),
        )


class MockLLMClient:
    """Deterministic local text generator used for the offline demo."""

    def generate_text(
        self,
        *,
        task: str,
        materials: Any,
        bullet_count: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> str:
        if task == "business_insights":
            return _generate_mock_business_insights(
                materials,
                bullet_count=bullet_count,
            )

        text = _normalize_materials(materials)
        if not text:
            raise LLMError("Cannot generate text because the provided materials are empty.")

        sentences = _split_sentences(text)
        summary = sentences[0] if sentences else text
        if max_length is not None and len(summary) > max_length:
            summary = summary[:max_length].rstrip()

        count = bullet_count if bullet_count is not None else min(3, len(sentences))
        points = sentences[:count]
        if not points:
            points = [summary]

        heading = {
            "summary": "Summary",
            "report": "Report",
            "business_insights": "Business insights",
        }.get(task, "Generated text")
        bullet_lines = "\n".join(f"- {point}" for point in points)
        return f"{heading}:\n{summary}\n\nKey points:\n{bullet_lines}"

    def answer_with_sources(
        self,
        *,
        question: str,
        retrieved_chunks: Sequence[Mapping[str, Any]],
    ) -> str:
        excerpts = [
            " ".join(str(chunk.get("content", "")).split())
            for chunk in retrieved_chunks
            if str(chunk.get("content", "")).strip()
        ]
        if not excerpts:
            raise LLMError("Cannot answer because no supporting excerpts were provided.")
        return f"Answer based on the provided files:\n{excerpts[0]}"


class CompatibleLLMClient:
    """Minimal OpenAI-compatible chat completions client."""

    def __init__(self, settings: LLMSettings) -> None:
        missing_fields = [
            name
            for name, value in (
                ("LLM_API_KEY", settings.api_key),
                ("LLM_BASE_URL", settings.base_url),
                ("LLM_MODEL", settings.model),
            )
            if not value
        ]
        if missing_fields:
            raise LLMError(
                "LLM_MODE=compatible requires environment variables: "
                f"{', '.join(missing_fields)}"
            )
        self.settings = settings

    def generate_text(
        self,
        *,
        task: str,
        materials: Any,
        bullet_count: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> str:
        text = _normalize_materials(materials)
        if not text:
            raise LLMError("Cannot generate text because the provided materials are empty.")
        constraints = []
        if bullet_count is not None:
            constraints.append(f"Include {bullet_count} key points.")
        if max_length is not None:
            constraints.append(f"Keep the summary within {max_length} characters.")
        return self._chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "Generate text using only the user-provided materials. "
                        "Do not add unsupported facts."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Task: {task}\n"
                        f"{' '.join(constraints)}\n\n"
                        f"Materials:\n{text}"
                    ),
                },
            ]
        )

    def answer_with_sources(
        self,
        *,
        question: str,
        retrieved_chunks: Sequence[Mapping[str, Any]],
    ) -> str:
        source_text = "\n\n".join(
            f"[Source {index}] {str(chunk.get('content', '')).strip()}"
            for index, chunk in enumerate(retrieved_chunks, start=1)
        )
        if not source_text:
            raise LLMError("Cannot answer because no supporting excerpts were provided.")
        return self._chat_completion(
            [
                {
                    "role": "system",
                    "content": (
                        "Answer only from the provided source excerpts. "
                        "Do not use outside knowledge or invent facts. "
                        "If the excerpts are insufficient, state that clearly."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question:\n{question}\n\nSource excerpts:\n{source_text}",
                },
            ]
        )

    def _chat_completion(self, messages: List[Dict[str, str]]) -> str:
        assert self.settings.base_url is not None
        assert self.settings.api_key is not None
        assert self.settings.model is not None
        endpoint = f"{self.settings.base_url.rstrip('/')}/chat/completions"
        body = json.dumps(
            {
                "model": self.settings.model,
                "messages": messages,
                "temperature": 0,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        api_request = request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(
                api_request,
                timeout=LLM_REQUEST_TIMEOUT_SECONDS,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise LLMError(
                f"Compatible LLM request failed with HTTP status {exc.code}."
            ) from exc
        except error.URLError as exc:
            raise LLMError("Compatible LLM request could not reach the configured service.") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMError("Compatible LLM service returned an invalid JSON response.") from exc

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                "Compatible LLM service response does not contain assistant text."
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMError("Compatible LLM service returned an empty response.")
        return content.strip()


LLMClient = Union[MockLLMClient, CompatibleLLMClient]


def get_llm_client(settings: Optional[LLMSettings] = None) -> LLMClient:
    active_settings = settings or LLMSettings.from_environment()
    if active_settings.mode == "mock":
        return MockLLMClient()
    if active_settings.mode == "compatible":
        return CompatibleLLMClient(active_settings)
    raise LLMError("LLM_MODE must be either 'mock' or 'compatible'.")


def _normalize_materials(materials: Any) -> str:
    parts = list(_extract_text_parts(materials))
    return " ".join(" ".join(part.split()) for part in parts if part.strip()).strip()


def _extract_text_parts(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, Mapping):
        content = value.get("content")
        if isinstance(content, str):
            yield content
            return
        for key, item in value.items():
            if key in {"path", "source_path"}:
                continue
            yield from _extract_text_parts(item)
        return
    if isinstance(value, Iterable):
        for item in value:
            yield from _extract_text_parts(item)


def _split_sentences(text: str) -> List[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|(?<=[。！？])", text)
        if sentence.strip()
    ]


def _generate_mock_business_insights(
    materials: Any,
    *,
    bullet_count: Optional[int],
) -> str:
    records = _find_table_records(materials)
    if not records:
        raise LLMError("Cannot generate business insights because table records are empty.")

    count = bullet_count if bullet_count is not None else min(3, len(records))
    points = [
        ", ".join(f"{key}={value}" for key, value in record.items())
        for record in records[:count]
    ]
    highest_ranked = points[0]
    bullet_lines = "\n".join(f"- {point}" for point in points)
    return (
        "Business insights:\n"
        f"{bullet_lines}\n\n"
        "Recommendation:\n"
        f"- Prioritize the highest-ranked result: {highest_ranked}"
    )


def _find_table_records(value: Any) -> List[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        records = value.get("records")
        if isinstance(records, list) and all(
            isinstance(record, Mapping) for record in records
        ):
            return records
        for item in value.values():
            nested_records = _find_table_records(item)
            if nested_records:
                return nested_records
        return []
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        for item in value:
            nested_records = _find_table_records(item)
            if nested_records:
                return nested_records
    return []
