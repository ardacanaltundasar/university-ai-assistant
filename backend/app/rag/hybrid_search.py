import json
import logging
from pathlib import Path
from typing import Literal, TypedDict

from backend.app.api.schemas import RetrievalDebugPayload
from backend.app.rag.bm25_store import BM25StoreError, bm25_search
from backend.app.rag.bm25_store import tokenize as bm25_tokenize
from backend.app.rag.embeddings import EmbeddingError
from backend.app.rag.retrieval_debug import build_retrieval_debug_payload, log_retrieval_debug
from backend.app.rag.vector_store import VectorStoreError, vector_search

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GOLD_FAQ_PATH = PROJECT_ROOT / "data" / "raw" / "faq" / "gold_faq.json"

DEFAULT_VECTOR_WEIGHT = 0.65
DEFAULT_BM25_WEIGHT = 0.35
KEYWORD_BM25_WEIGHT = 0.45
KEYWORD_VECTOR_WEIGHT = 0.55
GOLD_SCORE_BONUS = 0.08

KEYWORD_TERMS = [
    "çap",
    "yandal",
    "akts",
    "tek ders",
    "üç ders",
    "harç",
    "transkript",
    "obs",
    "wi-fi",
    "wifi",
]

RetrievalMethod = Literal["vector", "bm25", "hybrid"]


class HybridSearchResult(TypedDict):
    text: str
    source: str
    page: int
    score: float
    chunk_id: str
    file_name: str
    category: str
    priority: str
    retrieval_method: RetrievalMethod
    title: str
    url: str
    source_type: str


class _MergedEntry(TypedDict):
    text: str
    source: str
    page: int
    chunk_id: str
    file_name: str
    category: str
    priority: str
    title: str
    url: str
    source_type: str
    vector_score: float
    bm25_score: float
    from_vector: bool
    from_bm25: bool


def _normalize_scores(scores: list[float]) -> list[float]:
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi == lo:
        return [1.0] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]


def _resolve_weights(query: str) -> tuple[float, float]:
    q = query.lower()
    for term in KEYWORD_TERMS:
        if term in q:
            return KEYWORD_VECTOR_WEIGHT, KEYWORD_BM25_WEIGHT
    return DEFAULT_VECTOR_WEIGHT, DEFAULT_BM25_WEIGHT


def _load_gold_faq() -> list[dict]:
    if not GOLD_FAQ_PATH.exists():
        return []
    try:
        with GOLD_FAQ_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Gold FAQ okunamadı: %s", exc)
        return []


def search_gold_faq(query: str, top_k: int = 3) -> list[HybridSearchResult]:
    """Gold FAQ içinde basit token eşleşmesi ile arama."""
    items = _load_gold_faq()
    if not items:
        return []

    query_tokens = set(bm25_tokenize(query))
    if not query_tokens:
        return []

    scored: list[tuple[float, dict]] = []
    for item in items:
        question = item.get("question", "")
        q_tokens = set(bm25_tokenize(question))
        if not q_tokens:
            continue
        overlap = len(query_tokens & q_tokens) / len(query_tokens)
        if overlap >= 0.3 or query.lower() in question.lower():
            scored.append((overlap, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    results: list[HybridSearchResult] = []
    for rank, (match_score, item) in enumerate(scored[:top_k]):
        page = item.get("page")
        results.append(
            HybridSearchResult(
                text=item.get("answer", ""),
                source=item.get("source", "Öğrenci İşleri SSS"),
                page=int(page) if page is not None else 0,
                score=max(match_score, 0.5 - rank * 0.1),
                chunk_id=item.get("id", f"faq_{rank}"),
                file_name="gold_faq.json",
                category=item.get("category", "Genel"),
                priority="gold",
                retrieval_method="hybrid",
                title="",
                url="",
                source_type="faq",
            )
        )
    return results


def _apply_normalized(
    results: list,
    merged: dict[str, _MergedEntry],
    *,
    field: Literal["vector_score", "bm25_score"],
    flag: Literal["from_vector", "from_bm25"],
) -> None:
    raw_scores = [float(r["score"]) for r in results]
    norm_scores = _normalize_scores(raw_scores)
    for r, norm in zip(results, norm_scores, strict=True):
        cid = r["chunk_id"]
        if cid not in merged:
            merged[cid] = _MergedEntry(
                text=r["text"],
                source=r["source"],
                page=int(r["page"]),
                chunk_id=cid,
                file_name=r.get("file_name", ""),
                category=r.get("category", "Genel"),
                priority=r.get("priority", "static"),
                title=r.get("title", ""),
                url=r.get("url", ""),
                source_type=r.get("source_type", ""),
                vector_score=0.0,
                bm25_score=0.0,
                from_vector=False,
                from_bm25=False,
            )
        entry = merged[cid]
        entry[field] = norm
        entry[flag] = True
        if field == "vector_score":
            entry["text"] = r["text"]
            entry["source"] = r["source"]
            entry["page"] = int(r["page"])
            entry["file_name"] = r.get("file_name", entry["file_name"])
            entry["category"] = r.get("category", entry["category"])
            entry["priority"] = r.get("priority", entry["priority"])
            entry["title"] = r.get("title", entry.get("title", ""))
            entry["url"] = r.get("url", entry.get("url", ""))
            entry["source_type"] = r.get("source_type", entry.get("source_type", ""))
        elif not entry["from_vector"]:
            entry["text"] = r["text"]
            entry["source"] = r["source"]
            entry["page"] = int(r["page"])
            entry["file_name"] = r.get("file_name", entry["file_name"])
            entry["category"] = r.get("category", entry["category"])
            entry["priority"] = r.get("priority", entry["priority"])
            entry["title"] = r.get("title", entry.get("title", ""))
            entry["url"] = r.get("url", entry.get("url", ""))
            entry["source_type"] = r.get("source_type", entry.get("source_type", ""))


def _gold_into_merged(gold_results: list[HybridSearchResult], merged: dict[str, _MergedEntry]) -> None:
    raw = [float(r["score"]) for r in gold_results]
    norm = _normalize_scores(raw)
    for r, n in zip(gold_results, norm, strict=True):
        cid = r["chunk_id"]
        if cid in merged:
            merged[cid]["priority"] = "gold"
            merged[cid]["vector_score"] = max(merged[cid]["vector_score"], n)
            merged[cid]["from_vector"] = True
        else:
            merged[cid] = _MergedEntry(
                text=r["text"],
                source=r["source"],
                page=int(r["page"]),
                chunk_id=cid,
                file_name=r["file_name"],
                category=r["category"],
                priority="gold",
                title=r.get("title", ""),
                url=r.get("url", ""),
                source_type=r.get("source_type", "faq"),
                vector_score=n,
                bm25_score=0.0,
                from_vector=True,
                from_bm25=False,
            )


def hybrid_search(
    query: str,
    top_k: int = 5,
    *,
    fetch_k: int | None = None,
    capture_debug: bool = False,
) -> list[HybridSearchResult] | tuple[list[HybridSearchResult], RetrievalDebugPayload]:
    """
    Vector + BM25 sonuçlarını chunk_id ile birleştirir, skorları ağırlıklı toplar.
    capture_debug=True ise (sonuçlar, RetrievalDebugPayload) döner.
    """
    query = query.strip()
    if not query:
        if capture_debug:
            empty = build_retrieval_debug_payload(query, [], [], [])
            return [], empty
        return []

    internal_k = fetch_k or max(top_k * 2, top_k)
    vector_w, bm25_w = _resolve_weights(query)
    merged: dict[str, _MergedEntry] = {}
    raw_vector: list = []
    raw_bm25: list = []

    try:
        raw_vector = vector_search(query, top_k=internal_k)
        _apply_normalized(raw_vector, merged, field="vector_score", flag="from_vector")
    except (VectorStoreError, EmbeddingError) as exc:
        logger.warning("Vector search atlandı: %s", exc.message)

    try:
        raw_bm25 = bm25_search(query, top_k=internal_k)
        _apply_normalized(raw_bm25, merged, field="bm25_score", flag="from_bm25")
    except BM25StoreError as exc:
        logger.warning("BM25 search atlandı: %s", exc.message)

    gold_results = search_gold_faq(query, top_k=3)
    if gold_results:
        _gold_into_merged(gold_results, merged)

    if not merged:
        logger.info(
            "Hybrid search sonuç döndürmedi. "
            "Chroma/BM25 indekslerini ve OPENAI_API_KEY değerini kontrol edin."
        )
        if capture_debug:
            debug = build_retrieval_debug_payload(query, raw_vector, raw_bm25, [])
            return [], debug
        return []

    final: list[HybridSearchResult] = []
    for entry in merged.values():
        combined = vector_w * entry["vector_score"] + bm25_w * entry["bm25_score"]
        if entry["priority"] == "gold":
            combined += GOLD_SCORE_BONUS

        if entry["from_vector"] and entry["from_bm25"]:
            method: RetrievalMethod = "hybrid"
        elif entry["from_vector"]:
            method = "vector"
        else:
            method = "bm25"

        final.append(
            HybridSearchResult(
                text=entry["text"],
                source=entry["source"],
                page=entry["page"],
                score=round(min(combined, 1.0), 4),
                chunk_id=entry["chunk_id"],
                file_name=entry["file_name"],
                category=entry["category"],
                priority=entry["priority"],
                retrieval_method=method,
                title=entry.get("title", ""),
                url=entry.get("url", ""),
                source_type=entry.get("source_type", ""),
            )
        )

    final.sort(key=lambda r: r["score"], reverse=True)
    ranked = final[:top_k]

    if capture_debug:
        debug = build_retrieval_debug_payload(query, raw_vector, raw_bm25, ranked)
        return ranked, debug

    return ranked


def hybrid_search_with_debug(
    query: str,
    top_k: int = 5,
    *,
    fetch_k: int | None = None,
    log_to_terminal: bool = True,
) -> tuple[list[HybridSearchResult], RetrievalDebugPayload]:
    """Hybrid arama + debug payload; isteğe bağlı terminal logu."""
    result = hybrid_search(query, top_k=top_k, fetch_k=fetch_k, capture_debug=True)
    assert isinstance(result, tuple)
    documents, debug = result
    if log_to_terminal:
        log_retrieval_debug(debug)
    return documents, debug
