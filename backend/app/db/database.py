from __future__ import annotations

import logging
import time
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.app.core.config import get_database_url

logger = logging.getLogger(__name__)

Base = declarative_base()

_db_ready: bool = False
_engine: Any = None
SessionLocal: sessionmaker[Session] | None = None


def _build_engine():
    global _engine, SessionLocal
    url = get_database_url()
    if not url:
        raise ValueError(
            "DATABASE_URL tanımlı değil. "
            ".env dosyasına PostgreSQL bağlantı bilgisini ekleyin."
        )
    _engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine


def get_engine():
    global _engine
    if _engine is None:
        _build_engine()
    return _engine


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — DB oturumu."""
    if SessionLocal is None:
        _build_engine()
    assert SessionLocal is not None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database(*, max_retries: int = 10, retry_delay: float = 2.0) -> bool:
    """
    PostgreSQL bağlantısını doğrular ve tabloları oluşturur.
    Başarısız olursa False döner; uygulama RAG cevaplamaya devam edebilir.
    """
    global _db_ready
    url = get_database_url()
    if not url:
        logger.error(
            "DATABASE_URL eksik — PostgreSQL kalıcılığı devre dışı. "
            ".env.example dosyasındaki örneği kullanın."
        )
        _db_ready = False
        return False

    from backend.app.db import models  # noqa: F401 — modelleri kaydet

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            engine = get_engine()
            Base.metadata.create_all(bind=engine)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            _db_ready = True
            logger.info("Database initialized successfully")
            return True
        except Exception as exc:
            last_error = exc
            logger.warning(
                "PostgreSQL bağlantı denemesi %d/%d başarısız: %s",
                attempt,
                max_retries,
                exc,
            )
            if attempt < max_retries:
                time.sleep(retry_delay)

    _db_ready = False
    logger.error(
        "PostgreSQL başlatılamadı — kalıcılık devre dışı. Son hata: %s",
        last_error,
    )
    return False


def is_database_ready() -> bool:
    return _db_ready


def get_db_optional() -> Generator[Session | None, None, None]:
    """DB hazır değilse None döner — chat cevabı yine de üretilir."""
    if not _db_ready or SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_db() -> Generator[Session, None, None]:
    """DB zorunlu endpoint'ler için — hazır değilse hata."""
    from fastapi import HTTPException

    if not _db_ready:
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL şu anda kullanılamıyor. Lütfen daha sonra tekrar deneyin.",
        )
    yield from get_db()
