"""Yönetim paneli tanılama verileri — salt okunur; API anahtarı döndürülmez."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.core.config import (
    PROJECT_ROOT,
    bm25_path,
    chroma_path,
    get_settings,
    is_debug_retrieval_enabled,
    is_valid_openai_api_key,
    resolve_openai_api_key,
)
from backend.app.db import models
from backend.app.db.database import is_database_ready
from backend.app.rag.ingest import (
    CHUNKS_OUTPUT_FILE,
    RAW_PDF_DIR,
    RAW_SAMPLES_DIR,
    RAW_WEB_DIR,
)
from backend.app.rag.vector_store import is_vector_store_ready
from backend.app.cache.redis_cache import get_redis_client

logger = logging.getLogger(__name__)

TEXT_TRUNCATE = 120
KEY_SAMPLE_LIMIT = 8
RECENT_FILE_LIMIT = 5

ANSWER_CACHE_PREFIX = "answer_cache:"


def _truncate(text: str | None, *, limit: int = TEXT_TRUNCATE) -> str:
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _iso_mtime(path: Path) -> str | None:
    try:
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _count_glob(directory: Path, pattern: str) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for _ in directory.glob(pattern))


def _recent_files(directory: Path, pattern: str, *, limit: int = RECENT_FILE_LIMIT) -> list[dict[str, str]]:
    if not directory.is_dir():
        return []
    files = [p for p in directory.glob(pattern) if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, str]] = []
    for path in files[:limit]:
        out.append(
            {
                "name": path.name,
                "modified_at": _iso_mtime(path) or "",
            }
        )
    return out


def _include_sample_data() -> bool:
    raw = os.getenv("INCLUDE_SAMPLE_DATA", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _redis_status() -> str:
    settings = get_settings()
    try:
        client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        return "ready"
    except (redis.RedisError, OSError):
        return "unavailable"


def _redis_cache_stats() -> dict[str, Any]:
    status = _redis_status()
    out: dict[str, Any] = {
        "status": status,
        "answer_cache_key_count": 0,
        "sample_keys": [],
    }
    if status != "ready":
        return out

    client = get_redis_client()
    if client is None:
        out["status"] = "unavailable"
        return out

    count = 0
    samples: list[str] = []
    try:
        for key in client.scan_iter(match=f"{ANSWER_CACHE_PREFIX}*", count=100):
            count += 1
            if len(samples) < KEY_SAMPLE_LIMIT:
                decoded = key.decode() if isinstance(key, bytes) else str(key)
                samples.append(decoded)
    except (redis.RedisError, OSError) as exc:
        logger.warning("Redis scan failed: %s", exc)
        out["status"] = "unavailable"

    out["answer_cache_key_count"] = count
    out["sample_keys"] = samples
    return out


def _system_section() -> dict[str, Any]:
    settings = get_settings()
    api_configured = is_valid_openai_api_key(resolve_openai_api_key())
    chroma = chroma_path(settings)
    bm25 = bm25_path(settings)

    return {
        "backend": "ready",
        "database": "ready" if is_database_ready() else "unavailable",
        "redis": _redis_status(),
        "vector_db": "ready" if is_vector_store_ready() else "pending",
        "chroma_path": str(chroma),
        "chroma_collection": settings.chroma_collection_name,
        "chroma_exists": chroma.is_dir(),
        "bm25_index_path": str(bm25),
        "bm25_index_exists": bm25.is_file(),
        "openai_chat_model": settings.openai_chat_model,
        "openai_embedding_model": settings.openai_embedding_model,
        "openai_api_key_configured": api_configured,
        "debug_retrieval": is_debug_retrieval_enabled(),
        "enable_redis_cache": settings.enable_redis_cache,
        "redis_cache_ttl_seconds": settings.redis_cache_ttl_seconds,
    }


def _knowledge_base_section() -> dict[str, Any]:
    settings = get_settings()
    chroma = chroma_path(settings)
    bm25 = bm25_path(settings)

    return {
        "pdf_count": _count_glob(RAW_PDF_DIR, "*.pdf"),
        "web_json_count": _count_glob(RAW_WEB_DIR, "*.json"),
        "sample_count": _count_glob(RAW_SAMPLES_DIR, "*"),
        "include_sample_data": _include_sample_data(),
        "chroma_exists": chroma.is_dir(),
        "bm25_index_exists": bm25.is_file(),
        "chunks_jsonl_exists": CHUNKS_OUTPUT_FILE.is_file(),
        "recent_web_json": _recent_files(RAW_WEB_DIR, "*.json"),
        "recent_pdfs": _recent_files(RAW_PDF_DIR, "*.pdf"),
        "project_root": str(PROJECT_ROOT),
    }


def _postgres_section(db: Session | None) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "available": False,
        "chat_sessions": 0,
        "chat_messages": 0,
        "agent_runs": 0,
        "tool_calls": 0,
        "recent_agent_runs": [],
        "tool_usage_summary": [],
        "recent_tool_calls": [],
    }
    if db is None or not is_database_ready():
        return empty

    try:
        sessions = (
            db.query(func.count(models.ChatSession.id)).scalar() or 0
        )
        messages = (
            db.query(func.count(models.ChatMessage.id)).scalar() or 0
        )
        runs = db.query(func.count(models.AgentRun.id)).scalar() or 0
        tools = db.query(func.count(models.ToolCall.id)).scalar() or 0

        recent_runs = (
            db.query(models.AgentRun)
            .order_by(models.AgentRun.created_at.desc())
            .limit(10)
            .all()
        )
        usage_rows = (
            db.query(models.ToolCall.tool_name, func.count(models.ToolCall.id))
            .group_by(models.ToolCall.tool_name)
            .order_by(func.count(models.ToolCall.id).desc())
            .all()
        )
        recent_tools = (
            db.query(models.ToolCall)
            .order_by(models.ToolCall.created_at.desc())
            .limit(10)
            .all()
        )

        return {
            "available": True,
            "chat_sessions": int(sessions),
            "chat_messages": int(messages),
            "agent_runs": int(runs),
            "tool_calls": int(tools),
            "recent_agent_runs": [
                {
                    "question": _truncate(run.question),
                    "selected_tool": run.selected_tool,
                    "status": run.status,
                    "duration_ms": run.duration_ms,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                }
                for run in recent_runs
            ],
            "tool_usage_summary": [
                {"tool_name": name, "count": int(cnt)}
                for name, cnt in usage_rows
            ],
            "recent_tool_calls": [
                {
                    "tool_name": call.tool_name,
                    "status": call.status,
                    "output_summary": _truncate(call.output_summary),
                    "created_at": call.created_at.isoformat() if call.created_at else None,
                }
                for call in recent_tools
            ],
        }
    except Exception as exc:
        logger.warning("PostgreSQL diagnostics failed: %s", exc)
        return empty


def gather_admin_diagnostics(db: Session | None = None) -> dict[str, Any]:
    """Tam diagnostic payload — güvenli metadata only."""
    redis_stats = _redis_cache_stats()
    return {
        "system": _system_section(),
        "knowledge_base": _knowledge_base_section(),
        "redis": redis_stats,
        "postgres": _postgres_section(db),
    }
