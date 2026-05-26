from typing import TypedDict

from backend.app.api.schemas import Citation
from backend.app.rag.hybrid_search import HybridSearchResult

GOLD_SOURCE_LABEL = "Öğrenci İşleri SSS"


class CitationRecord(TypedDict):
    source: str
    page: int | None
    chunk_id: str
    file_name: str
    category: str
    priority: str


def _normalize_page(page: int | None) -> int | None:
    if page is None:
        return None
    try:
        value = int(page)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def document_to_citation(doc: HybridSearchResult) -> CitationRecord:
    priority = str(doc.get("priority", "static"))
    source = str(doc.get("source", "Bilinmeyen kaynak"))
    chunk_id = str(doc.get("chunk_id", ""))
    page = _normalize_page(doc.get("page"))

    if priority == "gold":
        source = source if source else GOLD_SOURCE_LABEL
        page = None

    return CitationRecord(
        source=source,
        page=page,
        chunk_id=chunk_id,
        file_name=str(doc.get("file_name", "")),
        category=str(doc.get("category", "Genel")),
        priority=priority,
    )


def deduplicate_citations(citations: list[CitationRecord]) -> list[CitationRecord]:
    """Aynı source + page + chunk_id tekrarlarını temizler."""
    seen: set[tuple[str, int | None, str]] = set()
    unique: list[CitationRecord] = []
    for citation in citations:
        key = (citation["source"], citation.get("page"), citation["chunk_id"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return unique


def build_citations(documents: list[HybridSearchResult]) -> list[CitationRecord]:
    if not documents:
        return []
    built = [document_to_citation(doc) for doc in documents]
    return deduplicate_citations(built)


def format_single_line(citation: CitationRecord, index: int) -> str:
    if citation["priority"] == "gold" or citation.get("page") is None:
        return f"{index}. {citation['source']}, {citation['chunk_id']}"
    return f"{index}. {citation['source']}, Sayfa {citation['page']}"


def format_citations_for_answer(citations: list[CitationRecord]) -> str:
    """Cevap metninin sonuna eklenecek Kaynaklar bloğu."""
    if not citations:
        return ""
    lines = ["", "Kaynaklar:"]
    for i, citation in enumerate(citations, start=1):
        lines.append(format_single_line(citation, i))
    return "\n".join(lines)


def to_api_citations(citations: list[CitationRecord]) -> list[Citation]:
    return [
        Citation(
            source=c["source"],
            page=c.get("page"),
            chunk_id=c["chunk_id"],
            file_name=c.get("file_name", ""),
            category=c.get("category", "Genel"),
            priority=c.get("priority", "static"),
        )
        for c in citations
    ]


def has_required_citations(citations: list[CitationRecord]) -> bool:
    return len(citations) > 0


def strip_sources_block(answer: str) -> str:
    """Cevap içindeki Kaynaklar bölümünü ayırır (frontend için)."""
    marker = "\n\nKaynaklar:"
    if marker in answer:
        return answer.split(marker, maxsplit=1)[0].strip()
    return answer.strip()
