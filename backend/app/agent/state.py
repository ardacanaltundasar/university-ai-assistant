import operator
from typing import Annotated, Literal, TypedDict

from backend.app.api.schemas import RetrievalDebugPayload
from backend.app.rag.hybrid_search import HybridSearchResult
from backend.app.services.citation_service import CitationRecord

ConfidenceLevel = Literal["low", "medium", "high", "unknown"]


class AgentState(TypedDict, total=False):
    # Girdi
    question: str

    # analyze_question / intent
    original_question: str
    normalized_question: str
    category: str
    needs_clarification: bool
    out_of_scope: bool
    out_of_scope_reason: str
    intent: str
    intent_reason: str
    selected_tool: str
    process_run_status: str

    # agent tooling
    agent_steps: Annotated[list[str], operator.add]
    tool_calls_log: list[dict]

    # route_question
    search_gold_faq: bool
    search_vector_db: bool
    search_bm25: bool
    category_filter: str | None

    # retrieve / grade
    documents: list[HybridSearchResult]
    retrieval_debug: RetrievalDebugPayload | None
    selected_documents: list[HybridSearchResult]
    documents_relevant: bool
    documents_sufficient: bool
    needs_rewrite: bool

    # rewrite
    rewritten_query: str | None
    rewrite_count: int

    # cevap
    answer: str
    citations: list[CitationRecord]
    confidence: ConfidenceLevel
    answer_valid: bool
    validation_warning: str | None
    validation_replaced_answer: bool
    llm_answer_generated: bool
    llm_response_empty: bool

    # izleme
    steps: Annotated[list[str], operator.add]
    error: str | None
