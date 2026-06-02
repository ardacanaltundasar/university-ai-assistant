import logging

import redis
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.agent.prompts import FALLBACK_MESSAGE
from backend.app.api.schemas import (
    AdminDiagnosticsResponse,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    SourceItem,
    SourcesResponse,
)
from backend.app.core.config import get_settings
from backend.app.db import crud
from backend.app.db.database import get_db_optional, is_database_ready, require_db
from backend.app.db.schemas import (
    ChatMessageListResponse,
    ChatMessageOut,
    ChatSessionCreate,
    ChatSessionListResponse,
    ChatSessionOut,
    DeleteSessionResponse,
    DocumentListResponse,
    DocumentMetadataOut,
    FeedbackCreate,
    FeedbackOut,
)
from backend.app.rag.ingest import CHUNKS_OUTPUT_FILE, IngestError, run_ingestion, summarize_sources
from backend.app.rag.vector_store import is_vector_store_ready
from backend.app.services.chat_persistence import run_chat_with_persistence
from backend.app.services.diagnostics_service import gather_admin_diagnostics

logger = logging.getLogger(__name__)

router = APIRouter()

MOCK_SOURCES: list[SourceItem] = [
    SourceItem(name="Kayıt Yönetmeliği", pages=12, chunks=32),
    SourceItem(name="Akademik Takvim", pages=4, chunks=8),
    SourceItem(name="Sınav Yönetmeliği", pages=18, chunks=45),
    SourceItem(name="ÇAP / Yandal Yönetmeliği", pages=10, chunks=24),
    SourceItem(name="Yaz Okulu Yönetmeliği", pages=6, chunks=14),
    SourceItem(name="Öğrenci İşleri SSS", pages=0, chunks=20),
]


def _redis_status() -> str:
    settings = get_settings()
    try:
        client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        return "ready"
    except (redis.RedisError, OSError):
        return "unavailable"


def _vector_db_status() -> str:
    if is_vector_store_ready():
        return "ready"
    if CHUNKS_OUTPUT_FILE.exists():
        return "pending"
    return "pending"


def _database_status() -> str:
    return "ready" if is_database_ready() else "unavailable"


def _parse_uuid(value: str, *, field: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Geçersiz {field}.") from exc


@router.get(
    "/admin/diagnostics",
    response_model=AdminDiagnosticsResponse,
    tags=["Yönetim Paneli"],
    summary="Yönetim paneli tanılama verileri",
)
def admin_diagnostics(
    db: Session | None = Depends(get_db_optional),
) -> AdminDiagnosticsResponse:
    """Sistem sağlığı ve gözlemlenebilirlik (salt okunur; API anahtarı döndürülmez)."""
    payload = gather_admin_diagnostics(db)
    return AdminDiagnosticsResponse.model_validate(payload)


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        api="running",
        vector_db=_vector_db_status(),
        redis=_redis_status(),
        database=_database_status(),
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    response_model_exclude_none=True,
    tags=["agent"],
)
def chat(
    request: ChatRequest,
    db: Session | None = Depends(get_db_optional),
) -> ChatResponse:
    try:
        return run_chat_with_persistence(db, request)
    except Exception as exc:
        logger.exception("/chat hatası: %s", exc)
        return ChatResponse(
            answer=FALLBACK_MESSAGE,
            citations=[],
            steps=[
                "Soru alındı.",
                "Beklenmeyen bir hata oluştu.",
                "Güvenli fallback cevabı döndürüldü.",
            ],
            confidence="unknown",
        )


@router.post("/chat/sessions", response_model=ChatSessionOut, tags=["chat"])
def create_chat_session(
    body: ChatSessionCreate,
    db: Session = Depends(require_db),
) -> ChatSessionOut:
    session = crud.create_chat_session(db, title=body.title)
    return ChatSessionOut.model_validate(session)


@router.get("/chat/sessions", response_model=ChatSessionListResponse, tags=["chat"])
def list_chat_sessions(db: Session = Depends(require_db)) -> ChatSessionListResponse:
    sessions = crud.list_chat_sessions(db)
    return ChatSessionListResponse(
        sessions=[ChatSessionOut.model_validate(s) for s in sessions]
    )


@router.delete(
    "/chat/sessions/{session_id}",
    response_model=DeleteSessionResponse,
    tags=["chat"],
)
def delete_chat_session(
    session_id: str,
    db: Session = Depends(require_db),
) -> DeleteSessionResponse:
    sid = _parse_uuid(session_id, field="session_id")
    if not crud.delete_chat_session(db, sid):
        raise HTTPException(status_code=404, detail="Sohbet oturumu bulunamadı.")
    return DeleteSessionResponse(success=True, message="Chat session deleted")


@router.get(
    "/chat/sessions/{session_id}/messages",
    response_model=ChatMessageListResponse,
    tags=["chat"],
)
def get_session_messages(
    session_id: str,
    db: Session = Depends(require_db),
) -> ChatMessageListResponse:
    sid = _parse_uuid(session_id, field="session_id")
    session = crud.get_chat_session(db, sid)
    if not session:
        raise HTTPException(status_code=404, detail="Sohbet oturumu bulunamadı.")
    messages = crud.list_session_messages(db, sid)
    return ChatMessageListResponse(
        session_id=sid,
        messages=[ChatMessageOut.model_validate(m) for m in messages],
    )


@router.post("/feedback", response_model=FeedbackOut, tags=["feedback"])
def submit_feedback(
    body: FeedbackCreate,
    db: Session = Depends(require_db),
) -> FeedbackOut:
    feedback = crud.create_feedback(
        db,
        message_id=body.message_id,
        rating=body.rating,
        comment=body.comment,
    )
    return FeedbackOut.model_validate(feedback)


@router.get("/documents", response_model=DocumentListResponse, tags=["documents"])
def list_documents(db: Session = Depends(require_db)) -> DocumentListResponse:
    docs = crud.list_documents(db)
    return DocumentListResponse(
        documents=[DocumentMetadataOut.model_validate(d) for d in docs]
    )


@router.get("/sources", response_model=SourcesResponse, tags=["data"])
def sources() -> SourcesResponse:
    if CHUNKS_OUTPUT_FILE.exists():
        summary = summarize_sources()
        if summary:
            return SourcesResponse(
                sources=[SourceItem(**item) for item in summary]
            )
    return SourcesResponse(sources=MOCK_SOURCES)


@router.post("/ingest", response_model=IngestResponse, tags=["data"])
def ingest(
    request: IngestRequest,
    db: Session | None = Depends(get_db_optional),
) -> IngestResponse:
    settings = get_settings()
    try:
        result = run_ingestion(rebuild=request.rebuild)
        if db is not None:
            try:
                summary = summarize_sources()
                if summary:
                    crud.sync_documents_from_summary(db, summary)
            except Exception as exc:
                logger.warning("Document metadata sync hatası: %s", exc)
                db.rollback()
        return IngestResponse(
            status=result["status"],
            chunks_indexed=result["chunks_indexed"],
            collection=settings.chroma_collection_name,
        )
    except IngestError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "message": exc.message,
                "error": exc.code,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Ingestion sırasında beklenmeyen bir hata oluştu.",
                "error": "ingest_failed",
            },
        ) from exc
