"""University Process Navigator — process_guidance intent düğümü."""

from __future__ import annotations

import logging

from backend.app.agent.state import AgentState
from backend.app.rag.hybrid_search import hybrid_search
from backend.app.tools.process_navigator import (
    build_process_search_query,
    build_process_tool_output,
    detect_process_type,
)

logger = logging.getLogger(__name__)


def run_process_guidance(state: AgentState) -> dict:
    """Süreç rehberi üretir; kaynak yoksa yetersiz kaynak mesajı döner."""
    question = state.get("normalized_question") or state["question"]
    process_type = detect_process_type(question)
    search_query = build_process_search_query(question, process_type)

    try:
        documents = hybrid_search(search_query, top_k=6)
    except Exception as exc:
        logger.exception("process_guidance retrieval hatası: %s", exc)
        documents = []

    try:
        result = build_process_tool_output(question=question, documents=documents)
    except Exception as exc:
        logger.exception("process_navigator hatası: %s", exc)
        return {
            "answer": (
                "Süreç rehberi şu anda hazırlanamadı. "
                "Lütfen daha sonra tekrar deneyin."
            ),
            "citations": [],
            "confidence": "unknown",
            "selected_tool": "process_navigator",
            "selected_documents": documents,
            "agent_steps": [
                "Niyet algılandı: process_guidance",
                f"Süreç türü belirlendi: {process_type}",
                "Süreç rehberi oluşturulurken hata oluştu",
            ],
            "tool_calls_log": [],
            "answer_valid": False,
            "steps": ["Process Navigator aracı hata verdi."],
        }

    run_status = result.get("run_status", "success")
    return {
        "answer": result["answer"],
        "citations": result.get("citations") or [],
        "confidence": result.get("confidence", "medium"),
        "selected_tool": "process_navigator",
        "selected_documents": documents,
        "agent_steps": result.get("agent_steps", []),
        "tool_calls_log": result.get("tool_calls", []),
        "answer_valid": run_status == "success",
        "process_run_status": run_status,
        "steps": result.get("agent_steps", []),
    }
