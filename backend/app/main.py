from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import load_env

load_env(reload_settings=True)

from backend.app.api.routes import router
from backend.app.core.logging import setup_logging
from backend.app.db.database import init_database

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if init_database():
        try:
            from backend.app.db.database import SessionLocal
            from backend.app.db import crud
            from backend.app.rag.ingest import CHUNKS_OUTPUT_FILE, summarize_sources

            if SessionLocal and CHUNKS_OUTPUT_FILE.exists():
                db = SessionLocal()
                try:
                    summary = summarize_sources()
                    if summary:
                        crud.sync_documents_from_summary(db, summary)
                finally:
                    db.close()
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Document metadata startup sync atlandı: %s", exc
            )
    yield


app = FastAPI(
    title="University AI Agent API",
    description="Üniversite Öğrenci İşleri AI Asistanı — PoC backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, tags=["api"])


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "University AI Agent API", "docs": "/docs", "health": "/health"}
