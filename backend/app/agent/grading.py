"""CRAG doküman değerlendirme — OpenAI + fallback."""

import logging

from backend.app.agent.prompts import DOCUMENT_GRADING_PROMPT, GRADING_SYSTEM
from backend.app.rag.hybrid_search import HybridSearchResult
from backend.app.services.openai_service import OpenAIServiceError, chat_json

logger = logging.getLogger(__name__)

MAX_DOCS_TO_GRADE = 5
SCORE_RELEVANT_FALLBACK = 0.35
SCORE_SUFFICIENT_FALLBACK = 0.55


class DocumentGradeResult:
    def __init__(
        self,
        *,
        is_relevant: bool,
        is_sufficient: bool,
        reason: str,
        used_fallback: bool = False,
    ) -> None:
        self.is_relevant = is_relevant
        self.is_sufficient = is_sufficient
        self.reason = reason
        self.used_fallback = used_fallback


def _heuristic_grade(doc: HybridSearchResult) -> DocumentGradeResult:
    score = float(doc.get("score", 0))
    is_rel = score >= SCORE_RELEVANT_FALLBACK
    is_suf = score >= SCORE_SUFFICIENT_FALLBACK and is_rel
    return DocumentGradeResult(
        is_relevant=is_rel,
        is_sufficient=is_suf,
        reason="Skor tabanlı fallback değerlendirme.",
        used_fallback=True,
    )


def grade_single_document(
    question: str,
    doc: HybridSearchResult,
) -> DocumentGradeResult:
    """Tek doküman için LLM CRAG değerlendirmesi."""
    excerpt = (doc.get("text") or "")[:1200]
    source = doc.get("source", "Bilinmeyen")
    user_prompt = DOCUMENT_GRADING_PROMPT.format(
        question=question,
        source=source,
        document=excerpt,
    )

    parsed = chat_json(system=GRADING_SYSTEM, user=user_prompt)
    if not parsed:
        return _heuristic_grade(doc)

    is_relevant = bool(parsed.get("is_relevant", False))
    is_sufficient = bool(parsed.get("is_sufficient", False))
    reason = str(parsed.get("reason", "LLM değerlendirmesi."))[:200]

    # Güvenilir kaynak: gold veya yönetmelik önceliği — yetersiz sufficient'i destekle
    priority = doc.get("priority", "")
    if is_relevant and priority == "gold" and not is_sufficient:
        is_sufficient = float(doc.get("score", 0)) >= 0.4

    return DocumentGradeResult(
        is_relevant=is_relevant,
        is_sufficient=is_sufficient,
        reason=reason,
        used_fallback=False,
    )


def grade_documents_batch(
    question: str,
    documents: list[HybridSearchResult],
) -> tuple[list[HybridSearchResult], list[HybridSearchResult], bool, bool]:
    """
    En fazla MAX_DOCS_TO_GRADE dokümanı değerlendirir.

    Returns:
        selected_documents, graded_candidates, any_relevant, any_sufficient
    """
    sorted_docs = sorted(
        documents,
        key=lambda d: float(d.get("score", 0)),
        reverse=True,
    )[:MAX_DOCS_TO_GRADE]

    selected: list[HybridSearchResult] = []
    any_relevant = False
    any_sufficient = False

    for doc in sorted_docs:
        try:
            result = grade_single_document(question, doc)
        except OpenAIServiceError:
            result = _heuristic_grade(doc)
        except Exception as exc:
            logger.warning("Doküman grading hatası (%s): %s", doc.get("chunk_id"), exc)
            result = _heuristic_grade(doc)

        if result.is_relevant:
            any_relevant = True
        if result.is_relevant and result.is_sufficient:
            any_sufficient = True
            selected.append(doc)

    return selected, sorted_docs, any_relevant, any_sufficient
