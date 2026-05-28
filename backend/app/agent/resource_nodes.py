"""Kaynak önerisi (Open Library) agent düğümleri."""

from __future__ import annotations

import logging

from backend.app.agent.intent import INACTIVE_INTENTS, Intent
from backend.app.agent.state import AgentState
from backend.app.rag.hybrid_search import hybrid_search
from backend.app.tools.resource_recommender import recommend_books_for_course

logger = logging.getLogger(__name__)

UNSUPPORTED_INTENT_MESSAGE = (
    "Bu özellik henüz desteklenmiyor. "
    "Şu an yönetmelik/duyuru soruları (RAG), üniversite süreç rehberi ve ders kaynak önerisi "
    "sunulmaktadır."
)


def run_resource_recommendation(state: AgentState) -> dict:
    """Open Library tabanlı kitap önerisi üretir."""
    question = state.get("normalized_question") or state["question"]

    documents = hybrid_search(question, top_k=5)
    context_parts = [d.get("text", "") for d in documents[:4] if d.get("text")]
    course_context = "\n\n".join(context_parts)

    try:
        result = recommend_books_for_course(question, course_context)
    except Exception as exc:
        logger.exception("resource_recommender hatası: %s", exc)
        return {
            "answer": (
                "Kaynak önerisi şu anda hazırlanamadı. "
                "Lütfen daha sonra tekrar deneyin."
            ),
            "citations": [],
            "confidence": "unknown",
            "selected_tool": "resource_recommender",
            "agent_steps": [
                "Niyet algılandı: resource_recommendation",
                "Kaynak önerisi sırasında hata oluştu",
            ],
            "tool_calls_log": [],
            "steps": ["Kaynak önerisi aracı hata verdi."],
        }

    return {
        "answer": result["answer"],
        "citations": [],
        "confidence": "medium",
        "selected_tool": "resource_recommender",
        "agent_steps": result.get("agent_steps", []),
        "tool_calls_log": result.get("tool_calls", []),
        "answer_valid": True,
        "steps": result.get("agent_steps", []),
    }


def unsupported_intent_response(state: AgentState) -> dict:
    """Aktif olmayan niyetler için dürüst yanıt."""
    intent: Intent = state.get("intent", "unknown")  # type: ignore[assignment]
    label = intent if intent in INACTIVE_INTENTS else "unknown"
    return {
        "answer": UNSUPPORTED_INTENT_MESSAGE,
        "citations": [],
        "confidence": "unknown",
        "selected_tool": f"unsupported_{label}",
        "agent_steps": [
            f"Niyet algılandı: {label}",
            "Bu özellik henüz desteklenmiyor",
        ],
        "tool_calls_log": [],
        "answer_valid": False,
        "steps": [f"Desteklenmeyen niyet: {label}"],
    }
