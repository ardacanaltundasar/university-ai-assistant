"""Redis answer cache — tekrarlayan sorularda agent/RAG/LLM maliyetini azaltır."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

import redis

from backend.app.agent.prompts import FALLBACK_MESSAGE
from backend.app.api.schemas import ChatResponse
from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None
_redis_unavailable_logged = False

CACHE_MISS_STEP = "Redis cache miss: agent akışı çalıştırıldı"
CACHE_SAVED_STEP = "Cevap Redis cache'e kaydedildi"
CACHE_HIT_STEP = "Redis cache hit: cevap önbellekten alındı"

_ERROR_STEP_MARKERS = (
    "Beklenmeyen bir hata",
    "Ajan akışı sırasında hata",
    "Cevap üretilemedi",
    "Güvenli fallback",
    "Boş soru",
)


def normalize_question(question: str) -> str:
    """Lower-case, trim, fazla boşlukları tek boşluğa indir; Türkçe karakterleri korur."""
    return re.sub(r"\s+", " ", question.strip().lower())


def build_answer_cache_key(question: str, intent: str | None = None) -> str:
    normalized = normalize_question(question)
    intent_part = intent or "unknown"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"answer_cache:{intent_part}:{digest}"


def _log_redis_unavailable() -> None:
    global _redis_unavailable_logged
    if not _redis_unavailable_logged:
        logger.warning("Redis cache unavailable, continuing without cache")
        _redis_unavailable_logged = True


def get_redis_client() -> redis.Redis | None:
    """Cache için Redis istemcisi; bağlantı hatasında None döner."""
    global _redis_client

    settings = get_settings()
    if not settings.enable_redis_cache:
        return None

    if _redis_client is not None:
        return _redis_client

    try:
        client = redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
            decode_responses=True,
        )
        client.ping()
        _redis_client = client
        return _redis_client
    except (redis.RedisError, OSError, ValueError):
        _log_redis_unavailable()
        return None


def get_cached_answer(question: str, intent: str | None = None) -> dict | None:
    client = get_redis_client()
    if client is None:
        return None

    key = build_answer_cache_key(question, intent=intent)
    try:
        raw = client.get(key)
        if not raw:
            return None
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not payload.get("answer"):
            return None
        return payload
    except (redis.RedisError, OSError, json.JSONDecodeError, TypeError):
        _log_redis_unavailable()
        return None


def set_cached_answer(
    question: str,
    payload: dict,
    intent: str | None = None,
    ttl_seconds: int | None = None,
) -> bool:
    client = get_redis_client()
    if client is None:
        return False

    settings = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else settings.redis_cache_ttl_seconds
    key = build_answer_cache_key(question, intent=intent)

    try:
        client.setex(key, ttl, json.dumps(payload, ensure_ascii=False))
        return True
    except (redis.RedisError, OSError, TypeError):
        _log_redis_unavailable()
        return False


def is_answer_cacheable(response: ChatResponse, agent_status: str) -> bool:
    """Yalnızca başarılı, anlamlı cevaplar cache'lenir."""
    if agent_status not in ("completed",):
        return False

    answer = (response.answer or "").strip()
    if not answer:
        return False
    if answer == FALLBACK_MESSAGE:
        return False
    if "yeterli bilgi yok" in answer:
        return False

    steps = response.agent_steps or response.steps or []
    for step in steps:
        for marker in _ERROR_STEP_MARKERS:
            if marker in step:
                return False
        if "insufficient_sources" in step.lower():
            return False

    return True


def response_to_cache_payload(response: ChatResponse, intent: str) -> dict:
    """ChatResponse → Redis cache payload."""
    agent_steps = [
        s
        for s in (response.agent_steps or response.steps or [])
        if s not in (CACHE_MISS_STEP, CACHE_SAVED_STEP, CACHE_HIT_STEP)
    ]
    return {
        "answer": response.answer,
        "sources": [c.model_dump() for c in response.citations],
        "agent_steps": agent_steps,
        "selected_tool": response.selected_tool,
        "intent": intent,
        "confidence": response.confidence,
        "validation_warning": response.validation_warning,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
