"""Cevap doğrulama — kaynaklara dayanma kontrolü (LLM + fallback)."""

import logging
from dataclasses import dataclass, field

from backend.app.agent.prompts import ANSWER_VALIDATION_PROMPT, VALIDATION_SYSTEM
from backend.app.rag.hybrid_search import HybridSearchResult
from backend.app.services.citation_service import CitationRecord, strip_sources_block
from backend.app.services.openai_service import chat_json

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 12_000
MAX_DOC_EXCERPT = 4_000


@dataclass
class AnswerValidationResult:
    is_grounded: bool
    unsupported_claims: list[str] = field(default_factory=list)
    reason: str = ""
    used_llm_fallback: bool = False


def _format_citations_summary(citations: list[CitationRecord]) -> str:
    if not citations:
        return "(boş)"
    lines = []
    for c in citations:
        page = c.get("page")
        page_text = f", sayfa {page}" if page is not None else ""
        lines.append(f"- {c['source']}{page_text}, chunk_id: {c['chunk_id']}")
    return "\n".join(lines)


def _format_source_context(documents: list[HybridSearchResult]) -> str:
    parts: list[str] = []
    total = 0
    for i, doc in enumerate(documents[:5], start=1):
        text = (doc.get("text") or "")[:MAX_DOC_EXCERPT]
        header = (
            f"[Kaynak {i}] {doc.get('source', '?')} | "
            f"chunk: {doc.get('chunk_id', '?')} | sayfa: {doc.get('page', '-')}"
        )
        block = f"{header}\n{text}"
        if total + len(block) > MAX_CONTEXT_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts) if parts else "(kaynak metni yok)"


def _parse_llm_validation(parsed: dict) -> AnswerValidationResult:
    is_grounded = bool(parsed.get("is_grounded", False))
    raw_claims = parsed.get("unsupported_claims", [])
    claims = (
        [str(c) for c in raw_claims if str(c).strip()]
        if isinstance(raw_claims, list)
        else []
    )
    reason = str(parsed.get("reason", "LLM değerlendirmesi."))[:300]
    return AnswerValidationResult(
        is_grounded=is_grounded,
        unsupported_claims=claims,
        reason=reason,
    )


def _heuristic_validation(
    answer_body: str,
    documents: list[HybridSearchResult],
) -> AnswerValidationResult:
    """LLM başarısız olduğunda basit metin örtüşmesi kontrolü."""
    combined = " ".join((d.get("text") or "").lower() for d in documents)
    body = answer_body.lower()
    if len(body) < 20:
        return AnswerValidationResult(
            is_grounded=False,
            reason="Cevap metni çok kısa.",
            used_llm_fallback=True,
        )
    keywords = [w for w in body.split() if len(w) > 5][:12]
    if not keywords:
        return AnswerValidationResult(
            is_grounded=False,
            reason="Doğrulanacak anahtar ifade bulunamadı.",
            used_llm_fallback=True,
        )
    hits = sum(1 for w in keywords if w in combined)
    ratio = hits / len(keywords)
    if ratio >= 0.4:
        return AnswerValidationResult(
            is_grounded=True,
            reason="Skor tabanlı fallback: cevap kaynak metniyle kısmen örtüşüyor.",
            used_llm_fallback=True,
        )
    return AnswerValidationResult(
        is_grounded=False,
        unsupported_claims=["Kaynak metinleriyle yeterli örtüşme bulunamadı."],
        reason="Skor tabanlı fallback: cevap kaynaklarla doğrulanamadı.",
        used_llm_fallback=True,
    )


def validate_answer_grounding(
    *,
    question: str,
    answer: str,
    documents: list[HybridSearchResult],
    citations: list[CitationRecord],
) -> AnswerValidationResult:
    """
    Cevabın kaynaklara dayanıp dayanmadığını kontrol eder.
    Ön koşul başarısızsa veya LLM grounded demezse is_grounded=False.
    """
    if not citations:
        return AnswerValidationResult(
            is_grounded=False,
            reason="Citation listesi boş — kaynaksız cevap kabul edilmez.",
        )
    if not documents:
        return AnswerValidationResult(
            is_grounded=False,
            reason="Seçili doküman yok — kaynaksız cevap kabul edilmez.",
        )

    answer_body = strip_sources_block(answer).strip()
    if not answer_body:
        return AnswerValidationResult(
            is_grounded=False,
            reason="Cevap metni boş.",
        )

    user_prompt = ANSWER_VALIDATION_PROMPT.format(
        question=question,
        answer=answer_body,
        context=_format_source_context(documents),
        citations=_format_citations_summary(citations),
    )

    try:
        parsed = chat_json(system=VALIDATION_SYSTEM, user=user_prompt)
    except Exception as exc:
        logger.warning("Answer validation LLM hatası: %s", exc)
        parsed = None

    if parsed is None:
        result = _heuristic_validation(answer_body, documents)
        if not result.is_grounded:
            result.reason = (
                "LLM doğrulama yapılamadı; güvenli modda cevap reddedildi."
            )
        return result

    result = _parse_llm_validation(parsed)
    if not result.is_grounded and not result.unsupported_claims:
        result.unsupported_claims = [
            result.reason or "Kaynaklarda desteklenmeyen ifadeler."
        ]
    return result
