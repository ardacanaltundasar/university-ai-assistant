"""Üniversite süreç rehberi — indexlenmiş kaynaklara dayalı adım adım yönlendirme."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.app.rag.hybrid_search import HybridSearchResult
from backend.app.services.citation_service import build_citations
from backend.app.services.openai_service import chat_json

logger = logging.getLogger(__name__)

PROCESS_TYPES = (
    "course_registration",
    "tuition_payment",
    "horizontal_transfer",
    "graduation",
    "excuse_exam",
    "registration_freeze",
    "document_forms",
    "academic_calendar",
    "general_process",
)

PROCESS_LABELS: dict[str, str] = {
    "course_registration": "Ders Seçimi ve Kayıt Yenileme",
    "tuition_payment": "Harç Ödeme İşlemleri",
    "horizontal_transfer": "Kurumlar Arası Yatay Geçiş",
    "graduation": "Mezuniyet Başvurusu",
    "excuse_exam": "Mazeret Sınavı Başvurusu",
    "registration_freeze": "Kayıt Dondurma",
    "document_forms": "Formlar ve Belgeler",
    "academic_calendar": "Akademik Takvim",
    "general_process": "Üniversite Süreci",
}

PROCESS_KEYWORDS: dict[str, list[str]] = {
    "course_registration": [
        "ders seç",
        "ders sec",
        "kayıt yenile",
        "kayit yenile",
        "ders kayıt",
        "ders kayit",
        "kayıt yenileme",
    ],
    "tuition_payment": ["harç", "harc", "katkı payı", "katki payi", "ödeme işlem"],
    "horizontal_transfer": ["yatay geçiş", "yatay gecis", "kurumlar arası"],
    "graduation": ["mezuniyet", "mezun ol"],
    "excuse_exam": ["mazeret sınav", "mazeret sinav"],
    "registration_freeze": ["kayıt dondur", "kayit dondur"],
    "document_forms": ["form", "dilekçe formu", "belge talep", "doküman"],
    "academic_calendar": ["akademik takvim", "takvim", "sınav tarih", "sinav tarih"],
}

PROCESS_SEARCH_BOOST: dict[str, list[str]] = {
    "course_registration": ["ders seçme", "kayıt yenileme", "danışman onay", "obs"],
    "tuition_payment": ["harç ödeme", "banka", "ödeme kanalı"],
    "horizontal_transfer": ["yatay geçiş", "başvuru", "kontenjan"],
    "graduation": ["mezuniyet", "diploma", "tek ders sınavı"],
    "excuse_exam": ["mazeret", "sınav başvuru"],
    "registration_freeze": ["kayıt dondurma", "ilişik kesme"],
    "document_forms": ["form", "öğrenci işleri form"],
    "academic_calendar": ["akademik takvim", "eğitim öğretim"],
    "general_process": ["öğrenci işleri", "başvuru süreci"],
}

MIN_RETRIEVAL_SCORE = 0.22
INSUFFICIENT_BODY = (
    "Eldeki kaynaklarda bu süreci tam çıkarmak için yeterli bilgi yok. "
    "Lütfen sorunuzu farklı kelimelerle tekrar deneyin veya ilgili birim "
    "duyurusunu indeksledikten sonra `ingest_data.py` çalıştırın."
)

PLAN_SYSTEM = (
    "Sen bir üniversite süreç rehberi asistanısın. "
    "Yalnızca verilen kaynak metinlerine dayan. Uydurma birim, tarih veya belge ekleme. "
    "Eksik bilgide ilgili alanı boş bırak veya açıkça belirt. Yalnızca geçerli JSON üret."
)

PLAN_PROMPT = """Kullanıcı sorusu:
{question}

Süreç türü: {process_type} ({process_label})

Kaynak metinleri:
{context}

Görev: Kaynaklara dayalı yapılandırılmış süreç planı üret.

Kurallar:
- steps: kaynakta geçen sıralı adımlar (en az 1, en fazla 12)
- documents_required: kaynakta açıkça geçen belgeler; yoksa boş liste
- cautions: tarih, süre, danışman, harç vb. kaynakta geçen uyarılar
- department: kaynakta geçen birim/kanal; yoksa null
- next_action: kullanıcının atması gereken tek mantıklı sonraki adım
- insufficient: kaynaklar süreci anlatmıyorsa true

JSON:
{{
  "process_name": "{process_label}",
  "summary": "2-4 cümle",
  "steps": ["..."],
  "documents_required": ["..."],
  "cautions": ["..."],
  "department": null,
  "next_action": "...",
  "insufficient": false,
  "insufficient_reason": ""
}}"""


def _normalize(q: str) -> str:
    return re.sub(r"\s+", " ", q.lower().strip())


def detect_process_type(user_question: str) -> str:
    """Soru metninden süreç türü tahmini."""
    q = _normalize(user_question)
    best = "general_process"
    best_score = 0
    for process_type, keywords in PROCESS_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in q)
        if hits > best_score:
            best_score = hits
            best = process_type
    return best


def build_process_search_query(user_question: str, process_type: str) -> str:
    """Hybrid search için genişletilmiş sorgu."""
    boost = PROCESS_SEARCH_BOOST.get(process_type, [])
    label = PROCESS_LABELS.get(process_type, "")
    parts = [user_question.strip(), label, *boost[:4]]
    return " ".join(dict.fromkeys(p for p in parts if p))


def _format_context_block(doc: HybridSearchResult, index: int) -> str:
    title = str(doc.get("title") or "").strip()
    url = str(doc.get("url") or "").strip()
    source = str(doc.get("source") or "Kaynak")
    page = doc.get("page") or 0
    header = f"[Kaynak {index}] {title or source}"
    if url:
        header += f" | URL: {url}"
    elif page and int(page) > 0:
        header += f" | Sayfa: {page}"
    text = (doc.get("text") or "").strip()[:5000]
    return f"{header}\n{text}"


def extract_process_facts(context: str, process_type: str) -> dict[str, Any]:
    """Kaynak metninden basit yapılandırılmış ipuçları çıkarır."""
    lines = [ln.strip() for ln in context.splitlines() if ln.strip()]
    step_candidates: list[str] = []
    for ln in lines:
        if re.match(r"^(\d+[\.\)]\s+|[-•*]\s+)", ln):
            step_candidates.append(re.sub(r"^(\d+[\.\)]\s+|[-•*]\s+)", "", ln).strip())

    date_hints = re.findall(
        r"\d{1,2}[\./]\d{1,2}[\./]\d{2,4}|\d{4}[-/]\d{2}|\w+\s+\d{4}",
        context,
        flags=re.IGNORECASE,
    )[:8]

    return {
        "process_type": process_type,
        "process_label": PROCESS_LABELS.get(process_type, process_type),
        "step_candidates": step_candidates[:15],
        "date_hints": date_hints,
        "context_length": len(context),
    }


def generate_process_plan(
    user_question: str,
    process_type: str,
    context: str,
    sources: list[HybridSearchResult],
) -> dict[str, Any]:
    """LLM ile yapılandırılmış süreç planı üretir."""
    label = PROCESS_LABELS.get(process_type, process_type)
    if not context.strip() or context.strip() == "(Kaynak metni bulunamadı.)":
        return {
            "process_name": label,
            "summary": "",
            "steps": [],
            "documents_required": [],
            "cautions": [],
            "department": None,
            "next_action": "",
            "insufficient": True,
            "insufficient_reason": "Kaynak metni yok",
        }

    source_refs = [
        {
            "source": d.get("source"),
            "title": d.get("title"),
            "url": d.get("url"),
            "page": d.get("page"),
            "chunk_id": d.get("chunk_id"),
        }
        for d in sources[:6]
    ]

    parsed = chat_json(
        system=PLAN_SYSTEM,
        user=PLAN_PROMPT.format(
            question=user_question,
            process_type=process_type,
            process_label=label,
            context=context[:14000],
        ),
        temperature=0.2,
        max_tokens=1200,
    )

    if not parsed:
        facts = extract_process_facts(context, process_type)
        steps = facts.get("step_candidates") or []
        return {
            "process_name": label,
            "summary": "Kaynak parçalarından otomatik özet oluşturulamadı.",
            "steps": steps[:8],
            "documents_required": [],
            "cautions": [],
            "department": None,
            "next_action": "İlgili birim duyurusunu okuyup adımları doğrulayın.",
            "insufficient": len(steps) < 1,
            "insufficient_reason": "LLM plan üretemedi",
            "source_refs": source_refs,
        }

    plan = {
        "process_name": str(parsed.get("process_name") or label),
        "summary": str(parsed.get("summary") or "").strip(),
        "steps": [str(s).strip() for s in (parsed.get("steps") or []) if str(s).strip()],
        "documents_required": [
            str(d).strip()
            for d in (parsed.get("documents_required") or [])
            if str(d).strip()
        ],
        "cautions": [str(c).strip() for c in (parsed.get("cautions") or []) if str(c).strip()],
        "department": parsed.get("department"),
        "next_action": str(parsed.get("next_action") or "").strip(),
        "insufficient": bool(parsed.get("insufficient")),
        "insufficient_reason": str(parsed.get("insufficient_reason") or "").strip(),
        "source_refs": source_refs,
    }
    if plan["department"] is not None:
        plan["department"] = str(plan["department"]).strip() or None

    if not plan["steps"] and not plan["summary"]:
        plan["insufficient"] = True
        plan["insufficient_reason"] = plan["insufficient_reason"] or "Yapılandırılmış adım bulunamadı"

    return plan


def format_process_answer(process_plan: dict[str, Any]) -> str:
    """Yapılandırılmış planı Markdown süreç rehberine dönüştürür."""
    name = process_plan.get("process_name") or "Üniversite Süreci"
    lines: list[str] = [f"# Süreç Rehberi: {name}", ""]

    summary = str(process_plan.get("summary") or "").strip()
    lines.append("## 1. Kısa Özet")
    lines.append(summary if summary else "Kaynaklarda özet bilgi sınırlıdır.")
    lines.append("")

    steps = process_plan.get("steps") or []
    lines.append("## 2. Adım Adım Süreç")
    if steps:
        for i, step in enumerate(steps, start=1):
            lines.append(f"{i}. {step}")
    else:
        lines.append("Kaynaklarda net adım listesi bulunamadı.")
    lines.append("")

    docs = process_plan.get("documents_required") or []
    lines.append("## 3. Gerekli Belgeler / Bilgiler")
    if docs:
        for doc in docs:
            lines.append(f"- {doc}")
    else:
        lines.append("Kaynaklarda gerekli belge listesi açıkça belirtilmemiştir.")
    lines.append("")

    cautions = process_plan.get("cautions") or []
    lines.append("## 4. Dikkat Edilmesi Gerekenler")
    if cautions:
        for c in cautions:
            lines.append(f"- {c}")
    else:
        lines.append("Kaynaklarda ek uyarı maddesi belirtilmemiştir.")
    lines.append("")

    dept = process_plan.get("department")
    lines.append("## 5. İlgili Birim / Başvuru Kanalı")
    if dept:
        lines.append(str(dept))
    else:
        lines.append("Kaynaklarda ilgili birim veya başvuru kanalı açıkça belirtilmemiştir.")
    lines.append("")

    next_action = str(process_plan.get("next_action") or "").strip()
    lines.append("## 6. Sonraki Aksiyon")
    lines.append(
        next_action
        if next_action
        else "Resmi duyuru veya öğrenci işleri sayfasındaki güncel talimatları kontrol edin."
    )
    lines.append("")

    lines.append("## 7. Kaynak Notu")
    lines.append(
        "Bu rehber yalnızca indekslenmiş kaynaklara göre üretilmiştir; "
        "resmi işlem yerine bilgilendirme amaçlıdır."
    )

    return "\n".join(lines)


def format_context_from_documents(documents: list[HybridSearchResult]) -> str:
    if not documents:
        return "(Kaynak metni bulunamadı.)"
    blocks = [_format_context_block(doc, i) for i, doc in enumerate(documents[:6], start=1)]
    return "\n\n".join(blocks)


def enrich_search_results(documents: list[HybridSearchResult]) -> list[HybridSearchResult]:
    """Vector/BM25 metadata alanlarını sonuç kayıtlarına taşır."""
    enriched: list[HybridSearchResult] = []
    for doc in documents:
        enriched.append(
            HybridSearchResult(
                text=doc.get("text", ""),
                source=doc.get("source", ""),
                page=int(doc.get("page", 0)),
                score=float(doc.get("score", 0)),
                chunk_id=doc.get("chunk_id", ""),
                file_name=doc.get("file_name", ""),
                category=doc.get("category", "Genel"),
                priority=doc.get("priority", "static"),
                retrieval_method=doc.get("retrieval_method", "hybrid"),
                title=str(doc.get("title") or ""),
                url=str(doc.get("url") or ""),
                source_type=str(doc.get("source_type") or ""),
            )
        )
    return enriched


def documents_sufficient_for_process(documents: list[HybridSearchResult]) -> bool:
    if not documents:
        return False
    top = max(float(d.get("score", 0)) for d in documents)
    return top >= MIN_RETRIEVAL_SCORE


def build_process_tool_output(
    *,
    question: str,
    documents: list[HybridSearchResult],
) -> dict[str, Any]:
    """Tam süreç navigasyon çıktısı: cevap, citations, plan, agent adımları."""
    docs = enrich_search_results(documents)
    process_type = detect_process_type(question)
    search_query = build_process_search_query(question, process_type)

    agent_steps = [
        "Niyet algılandı: process_guidance",
        f"Süreç türü belirlendi: {process_type}",
        "İlgili kaynaklar hybrid search ile arandı",
    ]

    if not documents_sufficient_for_process(docs):
        agent_steps.append("Durum: insufficient_sources")
        return {
            "answer": INSUFFICIENT_BODY,
            "citations": [],
            "confidence": "unknown",
            "process_type": process_type,
            "search_query": search_query,
            "process_plan": {"insufficient": True},
            "agent_steps": agent_steps,
            "tool_calls": [
                {
                    "tool_name": "process_navigator",
                    "input_summary": f"{process_type} | {search_query[:200]}",
                    "output_summary": "insufficient_sources",
                    "status": "insufficient_sources",
                }
            ],
            "run_status": "insufficient_sources",
        }

    context = format_context_from_documents(docs)
    facts = extract_process_facts(context, process_type)
    plan = generate_process_plan(question, process_type, context, docs)

    if plan.get("insufficient"):
        agent_steps.append("Durum: insufficient_sources")
        reason = plan.get("insufficient_reason") or ""
        answer = INSUFFICIENT_BODY
        if reason:
            answer += f"\n\n({reason})"
        return {
            "answer": answer,
            "citations": build_citations(docs[:5]),
            "confidence": "low",
            "process_type": process_type,
            "search_query": search_query,
            "process_plan": plan,
            "facts": facts,
            "agent_steps": agent_steps,
            "tool_calls": [
                {
                    "tool_name": "process_navigator",
                    "input_summary": f"{process_type} | {search_query[:200]}",
                    "output_summary": f"insufficient: {reason[:120]}",
                    "status": "insufficient_sources",
                }
            ],
            "run_status": "insufficient_sources",
        }

    agent_steps.extend(
        [
            "Süreç adımları çıkarıldı",
            "Checklist ve sonraki aksiyon oluşturuldu",
        ]
    )

    body = format_process_answer(plan)
    citations = build_citations(docs[:5])
    answer = body + format_citations_for_process(citations, docs[:5])

    return {
        "answer": answer,
        "citations": citations,
        "confidence": "medium",
        "process_type": process_type,
        "search_query": search_query,
        "process_plan": plan,
        "facts": facts,
        "agent_steps": agent_steps,
        "tool_calls": [
            {
                "tool_name": "process_navigator",
                "input_summary": f"{process_type} | {search_query[:200]}",
                "output_summary": json.dumps(
                    {"steps": len(plan.get("steps") or []), "process": plan.get("process_name")},
                    ensure_ascii=False,
                )[:500],
                "status": "success",
            }
        ],
        "run_status": "success",
    }


def format_citations_for_process(
    citations: list,
    documents: list[HybridSearchResult],
) -> str:
    """Web JSON (title+url) ve PDF kaynaklarını ayırt ederek Kaynaklar bloğu."""
    if not citations:
        return ""
    lines = ["", "Kaynaklar:"]
    for i, doc in enumerate(documents[:5], start=1):
        title = str(doc.get("title") or "").strip()
        url = str(doc.get("url") or "").strip()
        source = str(doc.get("source") or "")
        page = int(doc.get("page") or 0)
        file_name = str(doc.get("file_name") or "")
        st = str(doc.get("source_type") or "")

        if url and (st == "web" or source.endswith(".json") or title):
            label = title or file_name or source
            lines.append(f"{i}. {label} — {url}")
        elif page > 0:
            label = file_name or source
            lines.append(f"{i}. {label}, Sayfa {page}")
        else:
            lines.append(f"{i}. {source or file_name}")
    return "\n".join(lines)
