import logging
import re

from backend.app.agent.answer_generation import generate_llm_answer
from backend.app.agent.intent import INACTIVE_INTENTS, classify_intent
from backend.app.agent.grading import grade_documents_batch
from backend.app.agent.scope import is_out_of_scope
from backend.app.agent.validation import validate_answer_grounding
from backend.app.agent.prompts import (
    FALLBACK_MESSAGE,
    QUERY_REWRITE_PROMPT,
    REWRITE_SYSTEM,
)
from backend.app.agent.state import AgentState, ConfidenceLevel
from backend.app.core.config import is_debug_retrieval_enabled
from backend.app.rag.hybrid_search import hybrid_search, hybrid_search_with_debug
from backend.app.services.citation_service import (
    build_citations,
    format_citations_for_answer,
    has_required_citations,
)
from backend.app.services.openai_service import chat_json

logger = logging.getLogger(__name__)

MAX_REWRITE = 1

CATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("Sınavlar ve Notlar", ["sınav", "not", "tek ders", "üç ders", "büt", "mazeret", "harf not"]),
    ("Yönetmelik ve Akademik Haklar", ["kayıt dondur", "çap", "yandal", "yatay geçiş", "yaz okul", "kredi"]),
    ("Kayıt ve Harç İşlemleri", ["harç", "ders seç", "danışman", "akts", "kayıt yenile"]),
    ("Belge Talepleri", ["transkript", "belge", "mezun", "ilişik"]),
    ("Kampüs Yaşamı", ["obs", "kampüs", "kart", "wi-fi", "wifi", "yemekhane", "kütüphane"]),
]

REWRITE_EXPANSIONS: dict[str, list[str]] = {
    "mezun": ["mezuniyet", "tek ders sınavı", "üç ders sınavı"],
    "çap": ["çap başvuru", "çap ortalama", "çift anadal"],
    "yandal": ["yandal başvuru", "yandal ortalama"],
    "transkript": ["transkript alma", "öğrenci belgesi"],
    "harç": ["harç ödeme", "katkı payı", "banka"],
    "tek ders": ["tek ders sınavı", "mezuniyet"],
    "üç ders": ["üç ders sınavı", "başarısız ders"],
}


def _normalize_question(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _guess_category(question: str) -> str:
    q = question.lower()
    for category, keywords in CATEGORY_RULES:
        if any(kw in q for kw in keywords):
            return category
    return "Genel"


def _confidence_from_docs(docs: list, *, sufficient: bool) -> ConfidenceLevel:
    if not docs:
        return "unknown" if not sufficient else "low"
    top = max(float(d["score"]) for d in docs)
    if sufficient and top >= 0.7:
        return "high"
    if sufficient and top >= 0.45:
        return "medium"
    if sufficient:
        return "medium"
    return "low" if top >= 0.35 else "unknown"


def analyze_question(state: AgentState) -> dict:
    question = state["question"]
    normalized = _normalize_question(question)
    out_of_scope, scope_reason = is_out_of_scope(normalized)
    category = _guess_category(normalized)
    needs_clarification = len(normalized.split()) < 3

    intent, intent_reason = classify_intent(normalized)

    step = f"Soru analiz edildi — kategori: {category}, niyet: {intent}."
    if out_of_scope:
        step = f"Soru kapsam dışı tespit edildi: {scope_reason}."

    return {
        "original_question": question,
        "normalized_question": normalized,
        "category": category,
        "needs_clarification": needs_clarification,
        "out_of_scope": out_of_scope,
        "out_of_scope_reason": scope_reason,
        "intent": intent,
        "intent_reason": intent_reason,
        "steps": [step],
    }


def route_after_analyze(state: AgentState) -> str:
    if state.get("out_of_scope"):
        return "fallback_response"
    intent = state.get("intent", "rag_question")
    if intent == "resource_recommendation":
        return "resource_recommendation"
    if intent == "process_guidance":
        return "process_guidance"
    if intent in INACTIVE_INTENTS:
        return "unsupported_intent"
    return "route_question"


def route_question(state: AgentState) -> dict:
    category = state.get("category", "Genel")
    return {
        "selected_tool": "rag_search",
        "search_gold_faq": True,
        "search_vector_db": True,
        "search_bm25": True,
        "category_filter": category if category != "Genel" else None,
        "agent_steps": ["Niyet algılandı: rag_question"],
        "steps": [
            f"Arama yönlendirildi — Gold FAQ, vektör ve BM25 (filtre: {category})."
        ],
    }


def retrieve_documents(state: AgentState) -> dict:
    query = (
        state.get("rewritten_query")
        or state.get("normalized_question")
        or state["question"]
    )
    prefix = "Yeniden " if state.get("rewrite_count", 0) > 0 else ""

    if is_debug_retrieval_enabled():
        documents, debug = hybrid_search_with_debug(query, top_k=5, log_to_terminal=True)
        return {
            "documents": documents,
            "retrieval_debug": debug,
            "agent_steps": [f"{prefix}RAG araması yapıldı ({len(documents)} parça)"],
            "steps": [
                f"{prefix}Kaynaklarda arama yapıldı ({len(documents)} parça). "
                "[Retrieval debug aktif]"
            ],
        }

    documents = hybrid_search(query, top_k=5)
    return {
        "documents": documents,
        "agent_steps": [f"{prefix}RAG araması yapıldı ({len(documents)} parça)"],
        "steps": [f"{prefix}Kaynaklarda arama yapıldı ({len(documents)} parça)."],
    }


def grade_documents(state: AgentState) -> dict:
    documents = state.get("documents") or []
    question = state.get("normalized_question") or state["question"]

    if not documents:
        return {
            "documents_relevant": False,
            "documents_sufficient": False,
            "selected_documents": [],
            "needs_rewrite": True,
            "confidence": "unknown",
            "steps": ["Bulunan kaynaklar değerlendirildi — sonuç yok."],
        }

    selected, _candidates, any_relevant, any_sufficient = grade_documents_batch(
        question, documents
    )

    documents_sufficient = bool(selected)
    needs_rewrite = not documents_sufficient

    if documents_sufficient:
        confidence = _confidence_from_docs(selected, sufficient=True)
        step = "Bulunan kaynaklar doğrulandı."
    else:
        confidence: ConfidenceLevel = "low" if any_relevant else "unknown"
        step = "Bulunan kaynaklar yetersiz görüldü, alternatif arama hazırlanıyor."

    return {
        "documents_relevant": any_relevant,
        "documents_sufficient": documents_sufficient,
        "selected_documents": selected,
        "needs_rewrite": needs_rewrite,
        "confidence": confidence,
        "steps": [step],
    }


def _fallback_rewrite_queries(state: AgentState) -> list[str]:
    base = state.get("normalized_question") or state["question"]
    q_lower = base.lower()
    extra: list[str] = []

    for key, terms in REWRITE_EXPANSIONS.items():
        if key in q_lower:
            extra.extend(terms)

    category = state.get("category", "")
    if category and category != "Genel":
        extra.append(category)

    queries = [base]
    if extra:
        queries.append(" ".join(dict.fromkeys(extra)))
    return queries[:3]


def _llm_rewrite_queries(state: AgentState) -> list[str] | None:
    question = state.get("normalized_question") or state["question"]
    category = state.get("category", "Genel")
    user_prompt = QUERY_REWRITE_PROMPT.format(question=question, category=category)
    parsed = chat_json(system=REWRITE_SYSTEM, user=user_prompt)
    if not parsed:
        return None
    raw = parsed.get("queries", [])
    if not isinstance(raw, list):
        return None
    queries = [str(q).strip() for q in raw if str(q).strip()]
    return queries[:3] if queries else None


def rewrite_query(state: AgentState) -> dict:
    queries = _llm_rewrite_queries(state)
    if not queries:
        queries = _fallback_rewrite_queries(state)
        method = "fallback"
    else:
        method = "LLM"

    rewritten = " ".join(dict.fromkeys(queries))
    count = state.get("rewrite_count", 0) + 1

    return {
        "rewritten_query": rewritten,
        "rewrite_count": count,
        "steps": [
            f"Arama sorgusu yeniden yazıldı ({method}, deneme {count}): "
            f"«{rewritten[:80]}{'…' if len(rewritten) > 80 else ''}»"
        ],
    }


def generate_answer(state: AgentState) -> dict:
    docs = state.get("selected_documents") or []
    citations = build_citations(docs)
    question = state.get("normalized_question") or state["question"]

    if not docs or not citations:
        logger.info(
            "[ANSWER] LLM çağrısı yapıldı=False | yanıt boş=True | uzunluk=0"
        )
        return {
            "answer": "",
            "citations": [],
            "confidence": "unknown",
            "llm_answer_generated": False,
            "llm_response_empty": True,
            "steps": ["Cevap oluşturulamadı — kaynak bulunamadı."],
        }

    body, llm_called = generate_llm_answer(question, docs)
    llm_empty = not bool(body)

    if llm_empty:
        logger.info(
            "[ANSWER] LLM çağrısı yapıldı=%s | yanıt boş=True | uzunluk=0",
            llm_called,
        )
        return {
            "answer": "",
            "citations": citations,
            "confidence": "unknown",
            "llm_answer_generated": llm_called,
            "llm_response_empty": True,
            "steps": [
                "LLM cevap üretemedi veya boş yanıt döndü."
            ],
        }

    answer = body + format_citations_for_answer(citations)
    confidence = state.get("confidence") or _confidence_from_docs(docs, sufficient=True)

    logger.info(
        "[ANSWER] LLM çağrısı yapıldı=%s | yanıt boş=False | gövde uzunluğu=%d | "
        "toplam uzunluk (kaynaklar dahil)=%d",
        llm_called,
        len(body),
        len(answer),
    )

    return {
        "answer": answer,
        "citations": citations,
        "confidence": confidence,
        "llm_answer_generated": llm_called,
        "llm_response_empty": False,
        "validation_replaced_answer": False,
        "steps": [
            f"LLM ile cevap oluşturuldu ({len(citations)} kaynak, {len(body)} karakter)."
        ],
    }


def _downgrade_confidence(confidence: ConfidenceLevel) -> ConfidenceLevel:
    if confidence == "high":
        return "medium"
    if confidence == "medium":
        return "low"
    return confidence


def validate_answer(state: AgentState) -> dict:
    answer = (state.get("answer") or "").strip()
    documents = state.get("selected_documents") or []
    citations = state.get("citations") or build_citations(documents)
    question = state.get("normalized_question") or state.get("question", "")
    confidence: ConfidenceLevel = state.get("confidence", "unknown")
    answer_before = answer

    if not has_required_citations(citations) or not documents or not answer:
        logger.info(
            "[ANSWER] validation_replaced=False | final_length=%d | uyarı=önkoşul başarısız",
            len(answer),
        )
        return {
            "answer_valid": False,
            "validation_warning": "Cevap veya kaynak eksik — doğrulama atlandı.",
            "validation_replaced_answer": False,
            "citations": citations,
            "confidence": "unknown",
            "steps": ["Cevap doğrulanamadı (eksik kaynak veya boş metin)."],
        }

    try:
        result = validate_answer_grounding(
            question=question,
            answer=answer,
            documents=documents,
            citations=citations,
        )
    except Exception as exc:
        logger.warning("validate_answer hatası: %s", exc)
        warning = "Doğrulama sırasında teknik hata oluştu; cevap korundu."
        logger.info(
            "[ANSWER] validation_replaced=False | final_length=%d | uyarı=%s",
            len(answer_before),
            warning,
        )
        return {
            "answer_valid": False,
            "validation_warning": warning,
            "validation_replaced_answer": False,
            "citations": citations,
            "confidence": _downgrade_confidence(confidence),
            "steps": [warning],
        }

    if result.is_grounded:
        logger.info(
            "[ANSWER] validation_replaced=False | final_length=%d | grounded=True",
            len(answer_before),
        )
        return {
            "answer_valid": True,
            "validation_warning": None,
            "validation_replaced_answer": False,
            "citations": citations,
            "confidence": confidence,
            "steps": ["Cevabın kaynaklara dayandığı doğrulandı."],
        }

    warning_parts = [result.reason or "Cevap kaynaklarla tam örtüşmüyor."]
    if result.unsupported_claims:
        warning_parts.append(
            "Desteklenmeyen ifadeler: " + "; ".join(result.unsupported_claims[:3])
        )
    warning = " ".join(warning_parts)

    logger.info(
        "[ANSWER] validation_replaced=False | final_length=%d | grounded=False | %s",
        len(answer_before),
        warning[:200],
    )

    return {
        "answer_valid": False,
        "answer": answer_before,
        "validation_warning": warning,
        "validation_replaced_answer": False,
        "citations": citations,
        "confidence": _downgrade_confidence(confidence),
        "steps": [
            "Doğrulama uyarısı (cevap korundu): "
            + (warning[:160] + "…" if len(warning) > 160 else warning)
        ],
    }


def fallback_response(state: AgentState) -> dict:
    return {
        "answer": FALLBACK_MESSAGE,
        "citations": [],
        "confidence": "unknown",
        "selected_documents": [],
        "answer_valid": False,
        "needs_rewrite": False,
        "steps": ["Güvenli fallback cevabı döndürüldü."],
    }


def route_after_grade(state: AgentState) -> str:
    if state.get("documents_sufficient") and state.get("selected_documents"):
        return "generate_answer"
    if state.get("needs_rewrite") and state.get("rewrite_count", 0) < MAX_REWRITE:
        return "rewrite_query"
    return "fallback_response"


def route_after_validate(state: AgentState) -> str:
    """LLM cevabı varsa korunur; yalnızca boş cevapta fallback."""
    if (state.get("answer") or "").strip():
        return "__end__"
    return "fallback_response"
