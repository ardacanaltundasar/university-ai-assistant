"""Chat akışı için PostgreSQL kalıcılık — DB hatası RAG cevabını bozmaz."""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy.orm import Session

from backend.app.agent.graph import run_agent
from backend.app.agent.prompts import FALLBACK_MESSAGE
from backend.app.api.schemas import ChatRequest, ChatResponse
from backend.app.db import crud

logger = logging.getLogger(__name__)

_STEP_TOOL_MAP: list[tuple[str, str]] = [
    ("Niyet algılandı", "intent_router"),
    ("RAG araması", "hybrid_search"),
    ("Kaynaklarda arama", "hybrid_search"),
    ("Open Library", "open_library"),
    ("Ana konular", "topic_extractor"),
    ("Kitap önerileri", "resource_recommender"),
    ("LLM ile cevap", "generate_answer"),
    ("doğruland", "validate_answer"),
    ("Arama sorgusu", "rewrite_query"),
    ("fallback", "fallback_response"),
]


def _infer_tool_name(step: str) -> str:
    lower = step.lower()
    for needle, tool in _STEP_TOOL_MAP:
        if needle.lower() in lower:
            return tool
    return "agent_step"


def _parse_session_id(raw: str | None) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def _persist_tool_calls(
    db: Session,
    agent_run_id: uuid.UUID,
    response: ChatResponse,
    question: str,
) -> None:
    if response.tool_call_logs:
        for tc in response.tool_call_logs:
            crud.create_tool_call(
                db,
                agent_run_id=agent_run_id,
                tool_name=tc.tool_name,
                input_summary=tc.input_summary,
                output_summary=tc.output_summary,
                status=tc.status,
                duration_ms=tc.duration_ms,
            )
        return

    for step in response.agent_steps or response.steps:
        tool_name = _infer_tool_name(step)
        crud.create_tool_call(
            db,
            agent_run_id=agent_run_id,
            tool_name=tool_name,
            input_summary=question[:500] if tool_name == "hybrid_search" else None,
            output_summary=step[:500],
            status="completed",
        )


def run_chat_with_persistence(db: Session | None, request: ChatRequest) -> ChatResponse:
    """Agent çalıştırır; mümkünse mesajları ve agent run kayıtlarını PostgreSQL'e yazar."""
    session_uuid = _parse_session_id(request.session_id)
    question = request.question.strip()

    start = time.perf_counter()
    agent_status = "completed"
    response: ChatResponse | None = None

    try:
        response = run_agent(question)
    except Exception as exc:
        agent_status = "failed"
        logger.exception("Agent hatası (persistence devam ediyor): %s", exc)
        response = ChatResponse(
            answer=FALLBACK_MESSAGE,
            citations=[],
            steps=[
                "Soru alındı.",
                "Beklenmeyen bir hata oluştu.",
                "Güvenli fallback cevabı döndürüldü.",
            ],
            agent_steps=[
                "Soru alındı.",
                "Beklenmeyen bir hata oluştu.",
            ],
            selected_tool="rag_search",
            confidence="unknown",
        )

    duration_ms = int((time.perf_counter() - start) * 1000)

    if response is None:
        response = ChatResponse(
            answer=FALLBACK_MESSAGE,
            citations=[],
            steps=["Soru alındı.", "Cevap üretilemedi."],
            agent_steps=["Soru alındı.", "Cevap üretilemedi."],
            selected_tool="rag_search",
            confidence="unknown",
        )

    if db is None:
        return response

    try:
        session = None
        if session_uuid:
            session = crud.get_chat_session(db, session_uuid)
        if session is None:
            title = question[:80] or "Yeni Sohbet"
            session = crud.create_chat_session(db, title=title)
            session_uuid = session.id
        elif session.title in ("Yeni Sohbet", "") and question:
            crud.update_session_title(db, session, question[:80])

        user_message = crud.create_chat_message(
            db, session_id=session.id, role="user", content=question
        )
        assistant_message = crud.create_chat_message(
            db, session_id=session.id, role="assistant", content=response.answer
        )
        crud.touch_session(db, session)

        selected_tool = response.selected_tool or "rag_search"
        agent_run = crud.create_agent_run(
            db,
            session_id=session.id,
            question=question,
            selected_tool=selected_tool,
            status=agent_status,
            duration_ms=duration_ms,
        )

        _persist_tool_calls(db, agent_run.id, response, question)

        return response.model_copy(
            update={
                "session_id": str(session.id),
                "user_message_id": str(user_message.id),
                "assistant_message_id": str(assistant_message.id),
            }
        )
    except Exception as exc:
        logger.exception("PostgreSQL kalıcılık hatası (cevap korundu): %s", exc)
        db.rollback()

    return response
