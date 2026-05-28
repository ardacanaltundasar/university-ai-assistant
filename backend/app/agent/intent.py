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
    "process_guidance",
    "petition_generation",
    "weather_question",
    "unknown",
]

ACTIVE_INTENTS: frozenset[Intent] = frozenset(
    {"rag_question", "resource_recommendation", "process_guidance"}
)
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
    "dilekçe hazırla",
    "dilekce hazirla",
    "dilekçesi hazırla",
    "dilekcesi hazirla",
    "dilekçe",
    "dilekce",
    "petition",
    "başvuru metni yaz",
]

# Süreç rehberi — process_guidance
PROCESS_GUIDANCE_PHRASES: list[str] = [
    "nasıl yapılır",
    "nasil yapilir",
    "süreç nasıl",
    "surec nasil",
    "süreci nasıl",
    "sureci nasil",
    "süreci nasil",
    "adım adım",
    "adim adim",
    "hangi belgeler",
    "başvuru süreci",
    "basvuru sureci",
    "ne yapmam gerekiyor",
    "ne yapmam gerek",
    "nasıl ilerler",
    "nasil ilerler",
    "süreç nedir",
    "surec nedir",
    "nasıl işler",
    "nasil isler",
    "nasıl işliyor",
    "nasil isliyor",
]

# Genel bilgi / şart soruları — rag_question önceliği
RAG_INFO_PHRASES: list[str] = [
    "şartları nelerdir",
    "sartlari nelerdir",
    "şartlar neler",
    "sartlar neler",
    "kimler başvurabilir",
    "kimler basvurabilir",
    "kimler girebilir",
    "nedir",
    "nelerdir",
]

INTENT_CLASSIFIER_SYSTEM = (
    "Sen bir üniversite asistanı niyet sınıflandırıcısısın. "
    "Yalnızca geçerli JSON üret."
)

INTENT_CLASSIFIER_PROMPT = """Soru:
{question}

Sınıflar:
- rag_question: yönetmelik, kayıt, sınav, mezuniyet, belge, kampüs işlemleri (şartlar, kimler)
- process_guidance: adım adım süreç, nasıl yapılır, hangi belgeler, başvuru süreci
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


def _is_process_guidance_question(q: str) -> bool:
    """Süreç rehberi niyeti — şart/kimler sorularından ayrım."""
    if not _contains_any(q, PROCESS_GUIDANCE_PHRASES):
        return False
    if _contains_any(q, RAG_INFO_PHRASES) and not _contains_any(
        q,
        (
            "süreç",
            "surec",
            "adım",
            "adim",
            "nasıl yapılır",
            "nasil yapilir",
            "ne yapmam",
            "hangi belge",
            "başvuru süreci",
            "basvuru sureci",
        ),
    ):
        return False
    return True


def classify_intent_rules(question: str) -> Intent | None:
    """Keyword kuralları ile kesin eşleşme."""
    q = _normalize(question)

    if _contains_any(q, WEATHER_PHRASES):
        return "weather_question"
    if _contains_any(q, PETITION_PHRASES):
        return "petition_generation"

    resource_hit = _contains_any(q, RESOURCE_PHRASES)
    rag_hit = _contains_any(q, RAG_PHRASES)
    process_hit = _is_process_guidance_question(q)
    rag_info_hit = _contains_any(q, RAG_INFO_PHRASES)

    if resource_hit and not rag_hit and not process_hit:
        return "resource_recommendation"
    if resource_hit and rag_hit:
        if any(p in q for p in ("şart", "sart", "nelerdir", "kimler", "başvuru süresi")):
            if not any(
                p in q
                for p in ("kitap", "kaynak öner", "kaynak oner", "çalış", "calis", "okum")
            ):
                return "rag_question"
        return "resource_recommendation"

    if process_hit and not (rag_info_hit and "süreç" not in q and "surec" not in q):
        return "process_guidance"

    if rag_hit and not resource_hit:
        return "rag_question"
    if rag_info_hit and not process_hit:
        return "rag_question"

    if process_hit:
        return "process_guidance"

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
        "process_guidance",
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
