import logging

from langgraph.graph import END, START, StateGraph

from backend.app.agent.nodes import (
    analyze_question,
    fallback_response,
    generate_answer,
    grade_documents,
    retrieve_documents,
    rewrite_query,
    route_after_analyze,
    route_after_grade,
    route_after_validate,
    route_question,
    validate_answer,
)
from backend.app.agent.prompts import FALLBACK_MESSAGE
from backend.app.agent.state import AgentState
from backend.app.core.config import is_debug_retrieval_enabled
from backend.app.api.schemas import ChatResponse, ConfidenceLevel
from backend.app.services.citation_service import (
    build_citations,
    to_api_citations,
)

logger = logging.getLogger(__name__)

_compiled_graph = None


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("analyze_question", analyze_question)
    graph.add_node("route_question", route_question)
    graph.add_node("retrieve_documents", retrieve_documents)
    graph.add_node("grade_documents", grade_documents)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("validate_answer", validate_answer)
    graph.add_node("fallback_response", fallback_response)

    graph.add_edge(START, "analyze_question")
    graph.add_conditional_edges(
        "analyze_question",
        route_after_analyze,
        {
            "route_question": "route_question",
            "fallback_response": "fallback_response",
        },
    )
    graph.add_edge("route_question", "retrieve_documents")
    graph.add_edge("retrieve_documents", "grade_documents")
    graph.add_conditional_edges(
        "grade_documents",
        route_after_grade,
        {
            "generate_answer": "generate_answer",
            "rewrite_query": "rewrite_query",
            "fallback_response": "fallback_response",
        },
    )
    graph.add_edge("rewrite_query", "retrieve_documents")
    graph.add_edge("generate_answer", "validate_answer")
    graph.add_conditional_edges(
        "validate_answer",
        route_after_validate,
        {
            "__end__": END,
            "fallback_response": "fallback_response",
        },
    )
    graph.add_edge("fallback_response", END)

    return graph.compile()


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def state_to_chat_response(state: AgentState) -> ChatResponse:
    answer = state.get("answer") or FALLBACK_MESSAGE
    confidence: ConfidenceLevel = state.get("confidence") or "unknown"
    steps = state.get("steps") or ["Soru alındı."]

    if not steps or steps[0] != "Soru alındı.":
        steps = ["Soru alındı.", *steps]

    stored = state.get("citations")
    if stored:
        citations = stored
    else:
        citations = build_citations(state.get("selected_documents") or [])

    if confidence in ("high", "medium") and not citations:
        confidence = "low"

    retrieval_debug = None
    if is_debug_retrieval_enabled():
        retrieval_debug = state.get("retrieval_debug")

    validation_warning = state.get("validation_warning")

    logger.info(
        "[ANSWER] API yanıtı | final_length=%d | llm_generated=%s | llm_empty=%s | "
        "validation_warning=%s | validation_replaced=%s",
        len(answer),
        state.get("llm_answer_generated"),
        state.get("llm_response_empty"),
        bool(validation_warning),
        state.get("validation_replaced_answer", False),
    )

    return ChatResponse(
        answer=answer,
        citations=to_api_citations(citations),
        steps=steps,
        confidence=confidence,
        validation_warning=validation_warning,
        retrieval_debug=retrieval_debug,
    )


def run_agent(question: str) -> ChatResponse:
    """LangGraph ajan akışını çalıştırır ve ChatResponse döndürür."""
    global _compiled_graph
    question = question.strip()
    if not question:
        return ChatResponse(
            answer=FALLBACK_MESSAGE,
            citations=[],
            steps=["Soru alındı.", "Boş soru — güvenli yanıt döndürüldü."],
            confidence="unknown",
        )

    initial: AgentState = {
        "question": question,
        "steps": ["Soru alındı."],
        "rewrite_count": 0,
    }
    try:
        graph = get_compiled_graph()
        final_state = graph.invoke(initial)
        return state_to_chat_response(final_state)
    except Exception as exc:
        logger.exception("LangGraph ajan hatası: %s", exc)
        return ChatResponse(
            answer=FALLBACK_MESSAGE,
            citations=[],
            steps=[
                "Soru alındı.",
                "Ajan akışı sırasında hata oluştu.",
                "Güvenli fallback cevabı döndürüldü.",
            ],
            confidence="unknown",
        )
