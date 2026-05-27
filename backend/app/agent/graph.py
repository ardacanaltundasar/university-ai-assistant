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
from backend.app.agent.resource_nodes import (
    run_resource_recommendation,
    unsupported_intent_response,
)
from backend.app.agent.state import AgentState
from backend.app.core.config import is_debug_retrieval_enabled
from backend.app.api.schemas import ChatResponse, ConfidenceLevel, ToolCallLog
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
    graph.add_node("resource_recommendation", run_resource_recommendation)
    graph.add_node("unsupported_intent", unsupported_intent_response)

    graph.add_edge(START, "analyze_question")
    graph.add_conditional_edges(
        "analyze_question",
        route_after_analyze,
        {
            "route_question": "route_question",
            "resource_recommendation": "resource_recommendation",
            "unsupported_intent": "unsupported_intent",
            "fallback_response": "fallback_response",
        },
    )
    graph.add_edge("resource_recommendation", END)
    graph.add_edge("unsupported_intent", END)

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


def _build_agent_steps(state: AgentState, steps: list[str]) -> list[str]:
    agent_steps = list(state.get("agent_steps") or [])
    for s in steps:
        if s not in agent_steps:
            agent_steps.append(s)
    if not agent_steps or agent_steps[0] != "Soru alındı.":
        agent_steps = ["Soru alındı.", *agent_steps]
    return agent_steps


def _tool_calls_from_state(state: AgentState) -> list[ToolCallLog]:
    raw = state.get("tool_calls_log") or []
    logs: list[ToolCallLog] = []
    for item in raw:
        if isinstance(item, dict):
            logs.append(
                ToolCallLog(
                    tool_name=str(item.get("tool_name", "agent_step")),
                    input_summary=item.get("input_summary"),
                    output_summary=item.get("output_summary"),
                    status=str(item.get("status", "completed")),
                    duration_ms=item.get("duration_ms"),
                )
            )
    return logs


def state_to_chat_response(state: AgentState) -> ChatResponse:
    answer = state.get("answer") or FALLBACK_MESSAGE
    confidence: ConfidenceLevel = state.get("confidence") or "unknown"
    steps = state.get("steps") or ["Soru alındı."]
    agent_steps = _build_agent_steps(state, steps)

    stored = state.get("citations")
    if stored:
        citations = stored
    else:
        citations = build_citations(state.get("selected_documents") or [])

    if confidence in ("high", "medium") and not citations:
        if state.get("selected_tool") == "rag_search":
            confidence = "low"

    retrieval_debug = None
    if is_debug_retrieval_enabled():
        retrieval_debug = state.get("retrieval_debug")

    validation_warning = state.get("validation_warning")
    selected_tool = state.get("selected_tool") or "rag_search"

    logger.info(
        "[ANSWER] API yanıtı | final_length=%d | tool=%s | agent_steps=%d",
        len(answer),
        selected_tool,
        len(agent_steps),
    )

    return ChatResponse(
        answer=answer,
        citations=to_api_citations(citations),
        steps=steps,
        agent_steps=agent_steps,
        selected_tool=selected_tool,
        confidence=confidence,
        validation_warning=validation_warning,
        retrieval_debug=retrieval_debug,
        tool_call_logs=_tool_calls_from_state(state),
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
            agent_steps=["Soru alındı.", "Boş soru — güvenli yanıt döndürüldü."],
            selected_tool="rag_search",
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
            agent_steps=[
                "Soru alındı.",
                "Ajan akışı sırasında hata oluştu.",
            ],
            selected_tool="rag_search",
            confidence="unknown",
        )
