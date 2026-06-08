from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import MAX_DOCUMENT_CHUNKS
from core.workflow_schema import ExecutionContext


class RetrievalError(ValueError):
    """Raised when document retrieval input cannot be processed safely."""


def chunk_documents(
    documents: Sequence[Mapping[str, Any]],
    *,
    chunk_size: int,
    overlap: int,
) -> List[Dict[str, Any]]:
    if not documents:
        return []
    if chunk_size < 1:
        raise RetrievalError("chunk_size must be greater than zero.")
    if overlap < 0 or overlap >= chunk_size:
        raise RetrievalError("overlap must be non-negative and smaller than chunk_size.")

    chunks: List[Dict[str, Any]] = []
    for document in documents:
        source_name = str(document.get("name", "")).strip()
        source_path = str(document.get("path", "")).strip()
        content = document.get("content", "")
        if not source_name or not isinstance(content, str) or not content.strip():
            continue

        start_char = 0
        source_chunk_number = 1
        while start_char < len(content):
            end_char = min(start_char + chunk_size, len(content))
            excerpt = content[start_char:end_char]
            if excerpt.strip():
                chunks.append(
                    {
                        "chunk_id": (
                            f"{source_name}::chunk_{source_chunk_number:04d}"
                        ),
                        "source_name": source_name,
                        "source_path": source_path,
                        "content": excerpt,
                        "start_char": start_char,
                        "end_char": end_char,
                    }
                )
                source_chunk_number += 1
                if len(chunks) > MAX_DOCUMENT_CHUNKS:
                    raise RetrievalError(
                        "Document chunk count exceeds the "
                        f"{MAX_DOCUMENT_CHUNKS} chunk limit."
                    )
            if end_char == len(content):
                break
            start_char = end_char - overlap
    return chunks


def retrieve_relevant_chunks(
    chunks: Sequence[Mapping[str, Any]],
    *,
    query: str,
    top_k: int,
) -> List[Dict[str, Any]]:
    normalized_query = query.strip() if isinstance(query, str) else ""
    if not chunks or not normalized_query or top_k < 1:
        return []

    indexed_chunks = [
        (index, chunk, str(chunk.get("content", "")))
        for index, chunk in enumerate(chunks)
        if str(chunk.get("content", "")).strip()
    ]
    if not indexed_chunks:
        return []

    texts = [text for _, _, text in indexed_chunks]
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4))
    try:
        chunk_vectors = vectorizer.fit_transform(texts)
        query_vector = vectorizer.transform([normalized_query])
    except ValueError:
        return []
    if query_vector.nnz == 0:
        return []

    scores = cosine_similarity(query_vector, chunk_vectors).ravel()
    ranked_indexes = sorted(
        range(len(indexed_chunks)),
        key=lambda position: (-float(scores[position]), indexed_chunks[position][0]),
    )

    results = []
    for position in ranked_indexes:
        score = float(scores[position])
        if score <= 0:
            continue
        _, chunk, _ = indexed_chunks[position]
        results.append(
            {
                "chunk_id": str(chunk.get("chunk_id", "")),
                "source_name": str(chunk.get("source_name", "")),
                "source_path": str(chunk.get("source_path", "")),
                "content": str(chunk.get("content", "")),
                "score": score,
            }
        )
        if len(results) >= top_k:
            break
    return results


def chunk_document(
    inputs: Dict[str, Any],
    params: Dict[str, Any],
    context: ExecutionContext,
) -> Dict[str, Any]:
    documents = inputs.get("documents")
    if isinstance(documents, (str, bytes)) or not isinstance(documents, Sequence):
        raise RetrievalError("chunk_document requires a list of documents.")
    return {
        "chunks": chunk_documents(
            documents,
            chunk_size=params["chunk_size"],
            overlap=params["overlap"],
        )
    }


def retrieve_chunks(
    inputs: Dict[str, Any],
    params: Dict[str, Any],
    context: ExecutionContext,
) -> Dict[str, Any]:
    chunks = inputs.get("chunks")
    if isinstance(chunks, (str, bytes)) or not isinstance(chunks, Sequence):
        raise RetrievalError("retrieve_chunks requires a list of chunks.")
    return {
        "retrieved_chunks": retrieve_relevant_chunks(
            chunks,
            query=inputs.get("query", ""),
            top_k=params["top_k"],
        )
    }
