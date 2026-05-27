"""Open Library tabanlı akademik kitap kaynak önerici."""

from __future__ import annotations

import logging
import time
from typing import Any
import httpx

from backend.app.services.openai_service import chat_completion, chat_json

logger = logging.getLogger(__name__)

OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
REQUEST_TIMEOUT = 15.0
MAX_QUERIES = 5
BOOKS_PER_QUERY = 5
MAX_BOOKS_TOTAL = 12

TOPICS_SYSTEM = (
    "Sen bir akademik içerik analistisin. "
    "Verilen metinden ders konularını çıkar. Yalnızca geçerli JSON üret."
)

TOPICS_PROMPT = """Kullanıcı sorusu:
{question}

Ders / doküman bağlamı:
{context}

Görev: 5-10 ana konu başlığı çıkar (İngilizce, arama için uygun, kısa).
Bağlam yoksa sorudan çıkar.

JSON:
{{"topics": ["topic1", "topic2"]}}"""

RECOMMENDATION_SYSTEM = """Sen bir akademik kaynak danışmanısın.
Verilen ders içeriği, konular ve Open Library kitap listesine göre öğrenciye Türkçe cevap ver.
Uydurma kitap ekleme — yalnızca verilen kitapları kullan.
Her kitap için: başlık, seviye (Başlangıç/Orta/İleri), neden önerildi, Open Library linki.
Sonunda kısa çalışma stratejisi ver.
Madde madde, okunaklı yaz."""

RECOMMENDATION_USER = """Kullanıcı sorusu:
{question}

Öne çıkan konular:
{topics}

Open Library kitapları (JSON):
{books_json}

Cevap formatı örneği:
Bu ders içeriğine göre öne çıkan konular:
- ...

Önerilen kaynaklar:
1. [Başlık]
   Seviye: ...
   Neden önerildi: ...
   Open Library: [url]

Çalışma önerisi:
..."""


def extract_course_topics(course_context: str, user_question: str = "") -> list[str]:
    """LLM ile ana konu listesi çıkarır."""
    context = (course_context or "").strip()[:8000]
    if not context:
        context = "(Bağlam bulunamadı — yalnızca soru kullanılacak)"

    parsed = chat_json(
        system=TOPICS_SYSTEM,
        user=TOPICS_PROMPT.format(question=user_question, context=context),
        temperature=0.1,
        max_tokens=400,
    )
    if parsed and isinstance(parsed.get("topics"), list):
        topics = [str(t).strip() for t in parsed["topics"] if str(t).strip()]
        if topics:
            return topics[:10]

    return _fallback_topics_from_question(user_question)


def _fallback_topics_from_question(question: str) -> list[str]:
    q = question.lower()
    defaults = ["data structures", "algorithms", "computer science"]
    if "veri yapı" in q or "data struct" in q:
        return [
            "data structures",
            "linked list",
            "stack",
            "queue",
            "tree",
            "graph",
            "algorithm analysis",
        ]
    if "algoritma" in q or "algorithm" in q:
        return ["algorithms", "algorithm analysis", "sorting", "complexity"]
    return defaults


def build_book_search_queries(topics: list[str], user_question: str) -> list[str]:
    """Konulardan Open Library arama sorguları üretir."""
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        key = q.lower().strip()
        if key and key not in seen and len(key) > 3:
            seen.add(key)
            queries.append(q)

    q_lower = user_question.lower()
    if "veri yapı" in q_lower or "data struct" in q_lower:
        add("data structures algorithms")
        add("data structures programming")
    if "algoritma" in q_lower or "algorithm" in q_lower:
        add("introduction algorithms")
        add("algorithm analysis")

    for i, topic in enumerate(topics[:6]):
        add(topic)
        if i < 3:
            add(f"{topic} textbook")

    if not queries:
        add("computer science textbook")

    return queries[:MAX_QUERIES]


def search_open_library(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Open Library Search API — güvenli query parametresi."""
    query = query.strip()[:200]
    if not query:
        return []

    params = {
        "q": query,
        "limit": min(limit, 20),
        "language": "eng",
    }

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.get(OPEN_LIBRARY_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException:
        logger.warning("Open Library zaman aşımı: %s", query[:80])
        return []
    except httpx.HTTPError as exc:
        logger.warning("Open Library HTTP hatası: %s", exc)
        return []
    except Exception as exc:
        logger.warning("Open Library beklenmeyen hata: %s", exc)
        return []

    books: list[dict[str, Any]] = []
    for doc in payload.get("docs", [])[:limit]:
        if not isinstance(doc, dict):
            continue
        key = doc.get("key") or ""
        if not key:
            continue
        authors = doc.get("author_name") or []
        if isinstance(authors, list):
            author_str = ", ".join(str(a) for a in authors[:3])
        else:
            author_str = str(authors)

        cover_i = doc.get("cover_i")
        cover_url = (
            f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg" if cover_i else None
        )
        ol_url = f"https://openlibrary.org{key}" if key.startswith("/") else f"https://openlibrary.org{key}"

        subjects = doc.get("subject") or []
        if isinstance(subjects, list):
            subject_str = ", ".join(str(s) for s in subjects[:5])
        else:
            subject_str = str(subjects) if subjects else ""

        isbn_list = doc.get("isbn") or []
        isbn = isbn_list[0] if isinstance(isbn_list, list) and isbn_list else ""

        books.append(
            {
                "title": doc.get("title") or "Unknown title",
                "authors": author_str,
                "first_publish_year": doc.get("first_publish_year"),
                "isbn": str(isbn) if isbn else "",
                "openlibrary_key": key,
                "openlibrary_url": ol_url,
                "cover_url": cover_url,
                "subject": subject_str,
                "reason": "",
            }
        )
    return books


def deduplicate_books(books: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for book in books:
        key = book.get("openlibrary_key") or book.get("title", "")
        norm = str(key).lower().strip()
        if norm in seen:
            continue
        seen.add(norm)
        unique.append(book)
    return unique


def _format_topics_display(topics: list[str]) -> str:
    return "\n".join(f"- {t}" for t in topics)


def _books_summary_for_llm(books: list[dict[str, Any]]) -> str:
    import json

    slim = [
        {
            "title": b.get("title"),
            "authors": b.get("authors"),
            "first_publish_year": b.get("first_publish_year"),
            "openlibrary_url": b.get("openlibrary_url"),
            "subject": b.get("subject"),
        }
        for b in books[:MAX_BOOKS_TOTAL]
    ]
    return json.dumps(slim, ensure_ascii=False, indent=2)


def _answer_without_books(topics: list[str], user_question: str) -> str:
    topics_block = _format_topics_display(topics)
    return (
        "Open Library üzerinde yeterli kitap sonucu bulunamadı.\n\n"
        f"**Sorunuz:** {user_question}\n\n"
        "**Çıkarılan çalışma konuları:**\n"
        f"{topics_block}\n\n"
        "**Çalışma önerisi:**\n"
        "Yukarıdaki konuları sırayla çalışmanız önerilir. "
        "Üniversite kütüphanesi veya resmi ders kaynaklarınızı da kontrol edin. "
        "Uydurma kitap adı listelenmemiştir."
    )


def recommend_books_for_course(
    user_question: str,
    course_context: str,
) -> dict[str, Any]:
    """
    Tam kaynak öneri akışı.
    Dönüş: answer, topics, books, agent_steps, tool_calls
    """
    agent_steps: list[str] = [
        "Niyet algılandı: resource_recommendation",
    ]
    tool_calls: list[dict[str, Any]] = []

    if course_context.strip():
        agent_steps.append("Ders içeriği için RAG araması yapıldı")
    else:
        agent_steps.append("Ders bağlamı sınırlı — soru metni kullanıldı")

    t0 = time.perf_counter()
    topics = extract_course_topics(course_context, user_question)
    agent_steps.append(f"Ana konular çıkarıldı ({len(topics)} konu)")

    queries = build_book_search_queries(topics, user_question)
    all_books: list[dict[str, Any]] = []

    for query in queries:
        t_q = time.perf_counter()
        books = search_open_library(query, limit=BOOKS_PER_QUERY)
        duration_ms = int((time.perf_counter() - t_q) * 1000)
        tool_calls.append(
            {
                "tool_name": "open_library",
                "input_summary": query[:500],
                "output_summary": f"{len(books)} kitap",
                "status": "completed" if books else "empty",
                "duration_ms": duration_ms,
            }
        )
        all_books.extend(books)

    agent_steps.append("Open Library API çağrıldı")

    unique_books = deduplicate_books(all_books)[:MAX_BOOKS_TOTAL]

    if not unique_books:
        answer = _answer_without_books(topics, user_question)
        agent_steps.append("Kitap önerileri hazırlandı (API sonucu boş)")
        return {
            "answer": answer,
            "topics": topics,
            "books": [],
            "queries": queries,
            "agent_steps": agent_steps,
            "tool_calls": tool_calls,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        }

    books_json = _books_summary_for_llm(unique_books)
    llm_answer = chat_completion(
        system=RECOMMENDATION_SYSTEM,
        user=RECOMMENDATION_USER.format(
            question=user_question,
            topics=_format_topics_display(topics),
            books_json=books_json,
        ),
        temperature=0.3,
        max_tokens=1800,
    )

    if not llm_answer or not llm_answer.strip():
        answer = _build_structured_answer(topics, unique_books, user_question)
    else:
        answer = llm_answer.strip()

    agent_steps.append(f"Kitap önerileri hazırlandı ({len(unique_books)} kitap)")

    return {
        "answer": answer,
        "topics": topics,
        "books": unique_books,
        "queries": queries,
        "agent_steps": agent_steps,
        "tool_calls": tool_calls,
        "duration_ms": int((time.perf_counter() - t0) * 1000),
    }


def _build_structured_answer(
    topics: list[str],
    books: list[dict[str, Any]],
    user_question: str,
) -> str:
    lines = [
        "Bu ders içeriğine göre öne çıkan konular:",
        _format_topics_display(topics),
        "",
        "Önerilen kaynaklar:",
    ]
    for i, book in enumerate(books[:8], start=1):
        lines.append(f"{i}. **{book.get('title', 'Başlıksız')}**")
        if book.get("authors"):
            lines.append(f"   Yazar: {book['authors']}")
        lines.append("   Seviye: Orta")
        lines.append("   Neden önerildi: İlgili konu başlıklarıyla eşleşiyor.")
        lines.append(f"   Open Library: {book.get('openlibrary_url', '')}")
        lines.append("")
    lines.append(
        "**Çalışma önerisi:**\n"
        "Önce temel konularla başlayıp ilerledikçe daha kapsamlı kaynaklara geçmen önerilir."
    )
    return "\n".join(lines)
