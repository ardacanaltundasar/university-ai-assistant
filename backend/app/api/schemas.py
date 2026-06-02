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


class ToolCallLog(BaseModel):
    tool_name: str
    input_summary: str | None = None
    output_summary: str | None = None
    status: str = "completed"
    duration_ms: int | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    steps: list[str] = Field(default_factory=list)
    agent_steps: list[str] = Field(default_factory=list)
    selected_tool: str | None = None
    confidence: ConfidenceLevel
    session_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    validation_warning: str | None = None
    retrieval_debug: RetrievalDebugPayload | None = None
    tool_call_logs: list[ToolCallLog] | None = None


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


# --- Yönetim paneli tanılama (salt okunur) ---


class RecentFileEntry(BaseModel):
    name: str
    modified_at: str = ""


class DiagnosticsSystem(BaseModel):
    backend: str = "ready"
    database: str
    redis: str
    vector_db: str
    chroma_path: str
    chroma_collection: str
    chroma_exists: bool
    bm25_index_path: str
    bm25_index_exists: bool
    openai_chat_model: str
    openai_embedding_model: str
    openai_api_key_configured: bool
    debug_retrieval: bool
    enable_redis_cache: bool
    redis_cache_ttl_seconds: int


class DiagnosticsKnowledgeBase(BaseModel):
    pdf_count: int
    web_json_count: int
    sample_count: int
    include_sample_data: bool
    chroma_exists: bool
    bm25_index_exists: bool
    chunks_jsonl_exists: bool
    recent_web_json: list[RecentFileEntry] = Field(default_factory=list)
    recent_pdfs: list[RecentFileEntry] = Field(default_factory=list)
    project_root: str = ""


class DiagnosticsRedis(BaseModel):
    status: str
    answer_cache_key_count: int = 0
    sample_keys: list[str] = Field(default_factory=list)


class AgentRunDiagnostic(BaseModel):
    question: str
    selected_tool: str | None = None
    status: str
    duration_ms: int | None = None
    created_at: str | None = None


class ToolUsageSummary(BaseModel):
    tool_name: str
    count: int


class ToolCallDiagnostic(BaseModel):
    tool_name: str
    status: str
    output_summary: str = ""
    created_at: str | None = None


class DiagnosticsPostgres(BaseModel):
    available: bool = False
    chat_sessions: int = 0
    chat_messages: int = 0
    agent_runs: int = 0
    tool_calls: int = 0
    recent_agent_runs: list[AgentRunDiagnostic] = Field(default_factory=list)
    tool_usage_summary: list[ToolUsageSummary] = Field(default_factory=list)
    recent_tool_calls: list[ToolCallDiagnostic] = Field(default_factory=list)


class AdminDiagnosticsResponse(BaseModel):
    system: DiagnosticsSystem
    knowledge_base: DiagnosticsKnowledgeBase
    redis: DiagnosticsRedis
    postgres: DiagnosticsPostgres
