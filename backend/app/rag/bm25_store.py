import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from rank_bm25 import BM25Okapi

from backend.app.core.config import bm25_path, get_settings
from backend.app.rag.chunker import ChunkRecord

MIN_TOKEN_LEN = 2


class BM25StoreError(Exception):
    def __init__(self, message: str, code: str = "bm25_store_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class BM25SearchResult(TypedDict):
    text: str
    source: str
    page: int
    score: float
    chunk_id: str
    file_name: str
    category: str
    priority: str


@dataclass
class BM25IndexData:
    bm25: BM25Okapi
    chunks: list[ChunkRecord]


def tokenize(text: str) -> list[str]:
    """
    Türkçe metinler için basit tokenizer:
    lowercase → noktalama temizliği → boşlukla böl → kısa token filtrele.
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    tokens = text.split()
    return [t for t in tokens if len(t) >= MIN_TOKEN_LEN]


def build_bm25_index(chunks: list[ChunkRecord]) -> BM25IndexData:
    if not chunks:
        raise BM25StoreError("Indexlenecek chunk bulunamadı.", code="no_chunks")

    corpus = [tokenize(chunk["text"]) for chunk in chunks]
    if not any(corpus):
        raise BM25StoreError("Tokenize edilebilir metin bulunamadı.", code="empty_corpus")

    return BM25IndexData(bm25=BM25Okapi(corpus), chunks=chunks)


def save_bm25_index(data: BM25IndexData, path: Path | None = None) -> Path:
    target = path or bm25_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"bm25": data.bm25, "chunks": data.chunks}
    with target.open("wb") as f:
        pickle.dump(payload, f)
    return target


def load_bm25_index(path: Path | None = None) -> BM25IndexData:
    target = path or bm25_path()
    if not target.exists():
        raise BM25StoreError(
            f"BM25 index bulunamadı: {target}. Önce ingest çalıştırın.",
            code="index_missing",
        )

    with target.open("rb") as f:
        payload = pickle.load(f)

    return BM25IndexData(bm25=payload["bm25"], chunks=payload["chunks"])


def index_chunks_to_bm25(
    chunks: list[ChunkRecord],
    *,
    rebuild: bool = True,
    index_path: Path | None = None,
) -> int:
    """Chunk listesinden BM25 index oluşturur ve diske kaydeder."""
    target = index_path or bm25_path()
    if rebuild and target.exists():
        target.unlink()

    data = build_bm25_index(chunks)
    save_bm25_index(data, target)
    return len(chunks)


def _chunk_to_result(chunk: ChunkRecord, score: float) -> BM25SearchResult:
    return BM25SearchResult(
        text=chunk["text"],
        source=chunk["source"],
        page=int(chunk["page"]),
        score=float(score),
        chunk_id=chunk["chunk_id"],
        file_name=chunk["file_name"],
        category=chunk["category"],
        priority=chunk["priority"],
    )


def bm25_search(query: str, top_k: int = 5) -> list[BM25SearchResult]:
    """BM25 ile anahtar kelime araması."""
    data = load_bm25_index()
    query_tokens = tokenize(query)
    if not query_tokens:
        raise BM25StoreError(
            "Sorgu tokenize edilemedi. En az bir anlamlı kelime girin.",
            code="empty_query",
        )

    scores = data.bm25.get_scores(query_tokens)
    ranked_indices = sorted(
        range(len(scores)),
        key=lambda i: scores[i],
        reverse=True,
    )[:top_k]

    max_score = float(max(scores)) if len(scores) else 0.0
    results: list[BM25SearchResult] = []
    for rank, idx in enumerate(ranked_indices):
        raw = float(scores[idx])
        if max_score > 0:
            display_score = raw / max_score
        else:
            # Küçük corpus'ta BM25 skoru 0 gelebilir; sıralama korunur
            display_score = max(0.1, 1.0 - rank * 0.15)
        results.append(_chunk_to_result(data.chunks[idx], display_score))

    return results


def is_bm25_ready() -> bool:
    return bm25_path().exists()


def get_bm25_index_path() -> str:
    return str(bm25_path())
