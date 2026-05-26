"""Retrieval debug: terminal logları ve API payload yardımcıları."""

from __future__ import annotations

import logging
from typing import Any

from backend.app.api.schemas import RetrievalDebugChunk, RetrievalDebugPayload

logger = logging.getLogger(__name__)

TEXT_PREVIEW_MAX = 500

# Loglarda veya preview'da asla gösterilmemeli
_SENSITIVE_MARKERS = ("sk-proj", "sk-", "OPENAI_API_KEY", "api_key")


def text_preview(text: str, *, max_len: int = TEXT_PREVIEW_MAX) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[:max_len] + "…"


def _sanitize_preview(text: str) -> str:
    preview = text_preview(text)
    lower = preview.lower()
    for marker in _SENSITIVE_MARKERS:
        if marker.lower() in lower:
            return "[gizli içerik filtrelendi]"
    return preview


def result_to_debug_chunk(
    result: dict[str, Any],
    *,
    retrieval_method: str | None = None,
) -> RetrievalDebugChunk:
    method = retrieval_method or result.get("retrieval_method", "")
    page = result.get("page")
    return RetrievalDebugChunk(
        source=str(result.get("source", "")),
        page=int(page) if page is not None else None,
        chunk_id=str(result.get("chunk_id", "")),
        score=round(float(result.get("score", 0.0)), 4),
        text_preview=_sanitize_preview(str(result.get("text", ""))),
        file_name=str(result.get("file_name", "")),
        category=str(result.get("category", "")),
        retrieval_method=str(method) if method else None,
    )


def build_retrieval_debug_payload(
    question: str,
    chroma_results: list[dict[str, Any]],
    bm25_results: list[dict[str, Any]],
    final_contexts: list[dict[str, Any]],
) -> RetrievalDebugPayload:
    return RetrievalDebugPayload(
        question=question.strip(),
        chroma_results=[
            result_to_debug_chunk(r, retrieval_method="vector") for r in chroma_results
        ],
        bm25_results=[
            result_to_debug_chunk(r, retrieval_method="bm25") for r in bm25_results
        ],
        final_contexts=[
            result_to_debug_chunk(r) for r in final_contexts
        ],
    )


def log_retrieval_debug(payload: RetrievalDebugPayload) -> None:
    """Backend terminaline retrieval debug yazar (gizli anahtar yok)."""
    sep = "─" * 72
    logger.info("%s", sep)
    logger.info("[RETRIEVAL DEBUG] Soru: %s", payload.question)

    for label, chunks in (
        ("ChromaDB top_k", payload.chroma_results),
        ("BM25 top_k", payload.bm25_results),
        ("Hybrid final", payload.final_contexts),
    ):
        logger.info("[RETRIEVAL DEBUG] %s (%d)", label, len(chunks))
        for i, ch in enumerate(chunks, start=1):
            logger.info(
                "  #%d chunk_id=%s source=%s page=%s score=%.4f method=%s",
                i,
                ch.chunk_id,
                ch.source,
                ch.page if ch.page is not None else "—",
                ch.score,
                ch.retrieval_method or "—",
            )
            logger.info("      preview: %s", ch.text_preview)

    logger.info("%s", sep)
