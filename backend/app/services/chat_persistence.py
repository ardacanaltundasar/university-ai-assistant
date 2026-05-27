"""Chat akışı için PostgreSQL kalıcılık — DB hatası RAG cevabını bozmaz."""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy.orm import Session

from backend.app.agent.graph import run_agent
from backend.app.agent.intent import classify_intent_rules
from backend.app.agent.prompts import FALLBACK_MESSAGE
from backend.app.api.schemas import ChatRequest, ChatResponse, Citation, ToolCallLog
from backend.app.cache.redis_cache import (
    CACHE_HIT_STEP,
    CACHE_MISS_STEP,
    CACHE_SAVED_STEP,
    build_answer_cache_key,
    get_cached_answer,
    is_answer_cacheable,
    response_to_cache_payload,
    set_cached_answer,
)
from backend.app.core.config import get_settings
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
    ("Redis cache", "redis_cache"),
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


def _detect_intent_for_cache(question: str) -> str:
    """Cache key için kural tabanlı intent (LLM çağrısı yok)."""
    return classify_intent_rules(question) or "rag_question"


def _append_agent_step(response: ChatResponse, step: str) -> ChatResponse:
    steps = list(response.agent_steps or response.steps or [])
    if step not in steps:
        steps.append(step)
    return response.model_copy(update={"agent_steps": steps, "steps": steps})


def _prepend_agent_step(response: ChatResponse, step: str) -> ChatResponse:
    existing = list(response.agent_steps or response.steps or [])
    steps = [step, *[s for s in existing if s != step]]
    return response.model_copy(update={"agent_steps": steps, "steps": steps})


def _chat_response_from_cache(cached: dict) -> ChatResponse:
    sources = cached.get("sources") or []
    citations = [Citation(**item) for item in sources if isinstance(item, dict)]
    agent_steps = list(cached.get("agent_steps") or [])
    return ChatResponse(
        answer=cached.get("answer", ""),
        citations=citations,
        steps=agent_steps,
        agent_steps=agent_steps,
        selected_tool=cached.get("selected_tool"),
        confidence=cached.get("confidence") or "unknown",
        validation_warning=cached.get("validation_warning"),
    )


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
    """Agent veya Redis cache ile cevap üretir; mümkünse PostgreSQL'e yazar."""
    settings = get_settings()
    session_uuid = _parse_session_id(request.session_id)
    question = request.question.strip()
    intent = _detect_intent_for_cache(question)
    cache_key = build_answer_cache_key(question, intent=intent)

    start = time.perf_counter()
    agent_status = "completed"
    selected_tool_for_run: str | None = None
    response: ChatResponse | None = None

    if settings.enable_redis_cache:
        cached = get_cached_answer(question, intent=intent)
        if cached:
            agent_status = "cache_hit"
            selected_tool_for_run = "redis_cache"
            response = _prepend_agent_step(_chat_response_from_cache(cached), CACHE_HIT_STEP)
            response = response.model_copy(
                update={
                    "tool_call_logs": [
                        ToolCallLog(
                            tool_name="redis_cache",
                            input_summary=cache_key,
                            output_summary="cache hit",
                            status="hit",
                        )
                    ]
                }
            )

    if response is None:
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

        if settings.enable_redis_cache:
            response = _append_agent_step(response, CACHE_MISS_STEP)
            if is_answer_cacheable(response, agent_status):
                payload = response_to_cache_payload(response, intent)
                if set_cached_answer(question, payload, intent=intent):
                    response = _append_agent_step(response, CACHE_SAVED_STEP)

            cache_logs = list(response.tool_call_logs or [])
            cache_logs.append(
                ToolCallLog(
                    tool_name="redis_cache",
                    input_summary=cache_key,
                    output_summary="cache miss",
                    status="miss",
                )
            )
            response = response.model_copy(update={"tool_call_logs": cache_logs})

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

        selected_tool = selected_tool_for_run or response.selected_tool or "rag_search"
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
