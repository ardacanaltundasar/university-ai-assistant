from typing import Literal

from pydantic import BaseModel, Field


# --- Health ---


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    api: str = Field(..., examples=["running"])
    vector_db: str = Field(..., examples=["pending", "ready"])
    redis: str = Field(..., examples=["ready", "unavailable"])
    database: str = Field(..., examples=["ready", "unavailable"])


# --- Chat ---


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, examples=["Tek ders sınavına kimler girebilir?"])
    session_id: str | None = Field(
        default=None,
        description="Mevcut sohbet oturumu; yoksa yeni oturum oluşturulur.",
    )


class Citation(BaseModel):
    source: str
    page: int | None = None
    chunk_id: str
    file_name: str = ""
    category: str = "Genel"
    priority: str = "static"


ConfidenceLevel = Literal["low", "medium", "high", "unknown"]


class RetrievalDebugChunk(BaseModel):
    source: str
    page: int | None = None
    chunk_id: str
    score: float
    text_preview: str
    file_name: str = ""
    category: str = ""
    retrieval_method: str | None = None


class RetrievalDebugPayload(BaseModel):
    question: str
    chroma_results: list[RetrievalDebugChunk]
    bm25_results: list[RetrievalDebugChunk]
    final_contexts: list[RetrievalDebugChunk]


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    steps: list[str]
    confidence: ConfidenceLevel
    session_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    validation_warning: str | None = None
    retrieval_debug: RetrievalDebugPayload | None = None


# --- Sources ---


class SourceItem(BaseModel):
    name: str
    pages: int
    chunks: int


class SourcesResponse(BaseModel):
    sources: list[SourceItem]


# --- Ingest ---


class IngestRequest(BaseModel):
    rebuild: bool = Field(default=False, description="True ise mevcut indeksler yeniden oluşturulur.")


class IngestResponse(BaseModel):
    status: str = Field(..., examples=["success"])
    chunks_indexed: int
    collection: str
