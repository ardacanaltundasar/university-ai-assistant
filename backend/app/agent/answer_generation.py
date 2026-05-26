"""Kaynak parçalarından OpenAI ile tam cevap üretimi."""

from __future__ import annotations

import logging

from backend.app.agent.prompts import ANSWER_GENERATION_SYSTEM, ANSWER_GENERATION_USER_PROMPT
from backend.app.rag.hybrid_search import HybridSearchResult
from backend.app.services.openai_service import chat_completion

logger = logging.getLogger(__name__)

# LLM bağlamı — final cevap kırpılmaz; yalnızca modele giden CONTEXT sınırı
MAX_CONTEXT_CHARS = 16_000
MAX_CHUNK_CHARS = 6_000
DEFAULT_MAX_COMPLETION_TOKENS = 1500


def format_context_for_answer(documents: list[HybridSearchResult]) -> str:
    """Seçili kaynakların tam metnini CONTEXT bloğu olarak biçimlendirir."""
    if not documents:
        return "(Kaynak metni bulunamadı.)"

    blocks: list[str] = []
    total = 0
    for i, doc in enumerate(documents, start=1):
        text = (doc.get("text") or "").strip()
        if not text:
            continue
        if len(text) > MAX_CHUNK_CHARS:
            text = (
                text[:MAX_CHUNK_CHARS]
                + "\n[... kaynak parçası token sınırı nedeniyle kısaltıldı ...]"
            )
        header = (
            f"[Kaynak {i}] {doc.get('source', 'Bilinmeyen')} | "
            f"Sayfa: {doc.get('page', '-')} | chunk_id: {doc.get('chunk_id', '-')}"
        )
        block = f"{header}\n{text}"
        if total + len(block) > MAX_CONTEXT_CHARS:
            remaining = MAX_CONTEXT_CHARS - total
            if remaining > 300:
                blocks.append(block[:remaining] + "\n[... bağlam sınırı ...]")
            break
        blocks.append(block)
        total += len(block)

    return "\n\n".join(blocks) if blocks else "(Kaynak metni bulunamadı.)"


def generate_llm_answer(
    question: str,
    documents: list[HybridSearchResult],
    *,
    max_completion_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS,
) -> tuple[str, bool]:
    """
    OpenAI chat completion ile cevap üretir.
    Dönüş: (cevap_metni, llm_çağrısı_yapıldı_mı)
    """
    context = format_context_for_answer(documents)
    user_prompt = ANSWER_GENERATION_USER_PROMPT.format(
        question=question.strip(),
        context=context,
    )

    body = chat_completion(
        system=ANSWER_GENERATION_SYSTEM,
        user=user_prompt,
        temperature=0.2,
        max_tokens=max_completion_tokens,
    )
    llm_called = body is not None
    if not body or not body.strip():
        logger.warning(
            "[ANSWER] LLM yanıtı boş — soru uzunluğu=%d, context uzunluğu=%d",
            len(question),
            len(context),
        )
        return "", llm_called

    return body.strip(), llm_called
