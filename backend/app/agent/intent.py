"""Kullanıcı sorusu niyet sınıflandırması — keyword kuralları + isteğe bağlı LLM."""

from __future__ import annotations

import logging
import re
from typing import Literal

from backend.app.services.openai_service import chat_json

logger = logging.getLogger(__name__)

Intent = Literal[
    "rag_question",
    "resource_recommendation",
    "petition_generation",
    "weather_question",
    "unknown",
]

ACTIVE_INTENTS: frozenset[Intent] = frozenset({"rag_question", "resource_recommendation"})
INACTIVE_INTENTS: frozenset[Intent] = frozenset(
    {"petition_generation", "weather_question"}
)

# Kaynak önerisi — öncelikli eşleşme
RESOURCE_PHRASES: list[str] = [
    "kitap öner",
    "kitap oner",
    "kaynak öner",
    "kaynak oner",
    "kaynak tavsiye",
    "ders içeriğine göre",
    "ders içeriğine gore",
    "ne çalışmalıyım",
    "ne calismaliyim",
    "ne okumalıyım",
    "ne okumaliyim",
    "hangi kitap",
    "hangi kaynak",
    "bu pdf",
    "pdf'e göre",
    "pdf e gore",
    "algoritma kitab",
    "veri yapıları kaynak",
    "veri yapilari kaynak",
    "data structure",
    "open library",
    "çalışma kaynağı",
    "calisma kaynagi",
    "ders için kitap",
    "ders icin kitap",
    "akademik kaynak",
    "okuma listesi",
]

# Yönetmelik / öğrenci işleri — RAG
RAG_PHRASES: list[str] = [
    "kayıt dondur",
    "kayit dondur",
    "mazeret sınav",
    "mazeret sinav",
    "mezuniyet şart",
    "mezuniyet sart",
    "ders kayıt",
    "ders kayit",
    "kayıt yenile",
    "kayit yenile",
    "harç",
    "harç ödeme",
    "transkript",
    "tek ders sınav",
    "üç ders sınav",
    "yatay geçiş",
    "çap ",
    "yandal",
    "danışman onay",
    "obs şifre",
    "yönetmelik",
    "yonetmelik",
    "sınav tarih",
    "sinav tarih",
    "bütünleme",
    "butunleme",
    "akademik takvim",
    "ilişik kes",
]

WEATHER_PHRASES: list[str] = [
    "hava nasıl",
    "hava nasil",
    "hava kaç derece",
    "hava kac derece",
    "yağmur",
    "yagmur yağ",
]

PETITION_PHRASES: list[str] = [
    "dilekçe yaz",
    "dilekce yaz",
    "dilekçe oluştur",
    "petition",
    "başvuru metni yaz",
]

INTENT_CLASSIFIER_SYSTEM = (
    "Sen bir üniversite asistanı niyet sınıflandırıcısısın. "
    "Yalnızca geçerli JSON üret."
)

INTENT_CLASSIFIER_PROMPT = """Soru:
{question}

Sınıflar:
- rag_question: yönetmelik, kayıt, sınav, mezuniyet, belge, kampüs işlemleri
- resource_recommendation: ders için kitap/kaynak önerisi, ne çalışmalıyım, akademik okuma
- petition_generation: dilekçe veya başvuru metni yazdırma (henüz desteklenmiyor)
- weather_question: hava durumu (desteklenmiyor)
- unknown: belirsiz

Sadece JSON:
{{"intent": "rag_question", "reason": "kısa açıklama"}}"""


def _normalize(q: str) -> str:
    return re.sub(r"\s+", " ", q.lower().strip())


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(p in text for p in phrases)


def classify_intent_rules(question: str) -> Intent | None:
    """Keyword kuralları ile kesin eşleşme."""
    q = _normalize(question)

    if _contains_any(q, WEATHER_PHRASES):
        return "weather_question"
    if _contains_any(q, PETITION_PHRASES):
        return "petition_generation"

    resource_hit = _contains_any(q, RESOURCE_PHRASES)
    rag_hit = _contains_any(q, RAG_PHRASES)

    if resource_hit and not rag_hit:
        return "resource_recommendation"
    if rag_hit and not resource_hit:
        return "rag_question"
    if resource_hit and rag_hit:
        # "mezuniyet için kaynak öner" → resource; "mezuniyet şartları" → rag
        if any(p in q for p in ("şart", "sart", "nelerdir", "nasıl", "nasil", "kimler", "başvuru süresi")):
            if not any(p in q for p in ("kitap", "kaynak öner", "kaynak oner", "çalış", "calis", "okum")):
                return "rag_question"
        return "resource_recommendation"

    return None


def classify_intent_llm(question: str) -> Intent | None:
    parsed = chat_json(
        system=INTENT_CLASSIFIER_SYSTEM,
        user=INTENT_CLASSIFIER_PROMPT.format(question=question),
        temperature=0.0,
        max_tokens=120,
    )
    if not parsed:
        return None
    raw = str(parsed.get("intent", "")).strip()
    valid: list[Intent] = [
        "rag_question",
        "resource_recommendation",
        "petition_generation",
        "weather_question",
        "unknown",
    ]
    if raw in valid:
        return raw  # type: ignore[return-value]
    return None


def classify_intent(question: str, *, use_llm: bool = True) -> tuple[Intent, str]:
    """
    Niyet ve kısa gerekçe döner.
    Aktif olmayan niyetler tespit edilir ama çağıran taraf yönlendirir.
    """
    ruled = classify_intent_rules(question)
    if ruled:
        return ruled, f"Kural tabanlı: {ruled}"

    if use_llm:
        llm_intent = classify_intent_llm(question)
        if llm_intent:
            return llm_intent, f"LLM: {llm_intent}"

    return "rag_question", "Varsayılan: rag_question"
