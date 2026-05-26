from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.app.db import models


def create_chat_session(db: Session, *, title: str = "Yeni Sohbet") -> models.ChatSession:
    session = models.ChatSession(title=title[:255] or "Yeni Sohbet")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_chat_session(db: Session, session_id: uuid.UUID) -> models.ChatSession | None:
    return db.query(models.ChatSession).filter(models.ChatSession.id == session_id).first()


def list_chat_sessions(db: Session, *, limit: int = 50) -> list[models.ChatSession]:
    return (
        db.query(models.ChatSession)
        .order_by(desc(models.ChatSession.updated_at))
        .limit(limit)
        .all()
    )


def update_session_title(db: Session, session: models.ChatSession, title: str) -> models.ChatSession:
    session.title = title[:255] or session.title
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session


def touch_session(db: Session, session: models.ChatSession) -> None:
    session.updated_at = datetime.now(timezone.utc)
    db.commit()


def create_chat_message(
    db: Session,
    *,
    session_id: uuid.UUID,
    role: str,
    content: str,
) -> models.ChatMessage:
    message = models.ChatMessage(session_id=session_id, role=role, content=content)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def list_session_messages(
    db: Session, session_id: uuid.UUID
) -> list[models.ChatMessage]:
    return (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )


def create_feedback(
    db: Session,
    *,
    message_id: uuid.UUID | None,
    rating: str,
    comment: str | None = None,
) -> models.Feedback:
    feedback = models.Feedback(message_id=message_id, rating=rating, comment=comment)
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def upsert_document_metadata(
    db: Session,
    *,
    source: str,
    source_type: str,
    title: str,
    chunk_count: int,
    status: str = "indexed",
    url: str | None = None,
) -> models.DocumentMetadata:
    existing = (
        db.query(models.DocumentMetadata)
        .filter(models.DocumentMetadata.source == source)
        .first()
    )
    now = datetime.now(timezone.utc)
    if existing:
        existing.source_type = source_type
        existing.title = title
        existing.chunk_count = chunk_count
        existing.status = status
        existing.indexed_at = now
        if url is not None:
            existing.url = url
        db.commit()
        db.refresh(existing)
        return existing

    doc = models.DocumentMetadata(
        source=source,
        source_type=source_type,
        title=title,
        url=url,
        indexed_at=now,
        chunk_count=chunk_count,
        status=status,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def list_documents(db: Session) -> list[models.DocumentMetadata]:
    return (
        db.query(models.DocumentMetadata)
        .order_by(desc(models.DocumentMetadata.indexed_at.nullslast()))
        .all()
    )


def create_agent_run(
    db: Session,
    *,
    session_id: uuid.UUID | None,
    question: str,
    selected_tool: str | None,
    status: str,
    duration_ms: int | None,
) -> models.AgentRun:
    run = models.AgentRun(
        session_id=session_id,
        question=question,
        selected_tool=selected_tool,
        status=status,
        duration_ms=duration_ms,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def create_tool_call(
    db: Session,
    *,
    agent_run_id: uuid.UUID,
    tool_name: str,
    input_summary: str | None = None,
    output_summary: str | None = None,
    status: str = "completed",
    duration_ms: int | None = None,
) -> models.ToolCall:
    call = models.ToolCall(
        agent_run_id=agent_run_id,
        tool_name=tool_name,
        input_summary=input_summary,
        output_summary=output_summary,
        status=status,
        duration_ms=duration_ms,
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    return call


def sync_documents_from_summary(
    db: Session, summaries: list[dict], *, default_source_type: str = "pdf"
) -> None:
    for item in summaries:
        upsert_document_metadata(
            db,
            source=item["name"],
            source_type=item.get("source_type") or default_source_type,
            title=item["name"],
            chunk_count=int(item.get("chunks", 0)),
            status="indexed",
        )
