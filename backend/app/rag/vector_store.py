from __future__ import annotations

from typing import Any, TypedDict

import chromadb

from backend.app.core.config import chroma_path, get_settings
from backend.app.rag.chunker import ChunkRecord
from backend.app.rag.embeddings import EmbeddingError, embed_texts

UPSERT_BATCH_SIZE = 100

_chroma_client: Any = None


class VectorStoreError(Exception):
    def __init__(self, message: str, code: str = "vector_store_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class VectorSearchResult(TypedDict):
    text: str
    source: str
    page: int
    score: float
    chunk_id: str
    file_name: str
    category: str
    priority: str
    title: str
    url: str
    source_type: str


def get_chroma_client() -> Any:
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    settings = get_settings()
    path = chroma_path(settings)
    path.mkdir(parents=True, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(
        path=str(path.resolve()),
        settings=chromadb.Settings(
            anonymized_telemetry=False,
            allow_reset=True,
        ),
    )
    return _chroma_client


def get_collection(*, create: bool = True):
    settings = get_settings()
    client = get_chroma_client()
    name = settings.chroma_collection_name
    if create:
        return client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )
    return client.get_collection(name=name)


def reset_collection() -> None:
    settings = get_settings()
    client = get_chroma_client()
    try:
        client.delete_collection(settings.chroma_collection_name)
    except (ValueError, chromadb.errors.NotFoundError):
        pass


def _chunk_metadata(chunk: ChunkRecord) -> dict:
    """ChromaDB metadata — yalnızca str/int/float/bool değerler."""
    page = int(chunk.get("page", 0))
    return {
        "chunk_id": chunk["chunk_id"],
        "source": chunk["source"],
        "file_name": chunk.get("file_name", ""),
        "page": page,
        "category": chunk.get("category", "Genel"),
        "priority": chunk.get("priority", "static"),
        "source_type": chunk.get("source_type", "pdf"),
        "title": chunk.get("title", chunk["source"]),
        "content_type": chunk.get("content_type", "pdf"),
        "section_title": chunk.get("section_title", "") or "",
        "indexed_at": chunk.get("indexed_at", ""),
        "url": chunk.get("url", "") or "",
        "date": chunk.get("date", "") or "",
    }


def _distance_to_score(distance: float) -> float:
    """Cosine distance → benzerlik skoru (yüksek = daha alakalı)."""
    return max(0.0, 1.0 - float(distance))


def index_chunks_to_chroma(
    chunks: list[ChunkRecord],
    *,
    rebuild: bool = True,
) -> int:
    """Chunk listesini embed edip ChromaDB collection'a yazar."""
    if not chunks:
        raise VectorStoreError("Indexlenecek chunk bulunamadı.", code="no_chunks")

    if rebuild:
        reset_collection()

    collection = get_collection(create=True)
    indexed = 0

    for start in range(0, len(chunks), UPSERT_BATCH_SIZE):
        batch = chunks[start : start + UPSERT_BATCH_SIZE]
        texts = [c["text"] for c in batch]
        try:
            embeddings = embed_texts(texts)
        except EmbeddingError:
            raise

        collection.upsert(
            ids=[c["chunk_id"] for c in batch],
            documents=texts,
            metadatas=[_chunk_metadata(c) for c in batch],
            embeddings=embeddings,
        )
        indexed += len(batch)

    return indexed


def vector_search(query: str, top_k: int = 5) -> list[VectorSearchResult]:
    """Sorgu metni için semantic arama yapar."""
    if not query.strip():
        return []

    try:
        collection = get_collection(create=False)
    except (ValueError, chromadb.errors.NotFoundError) as exc:
        raise VectorStoreError(
            "ChromaDB collection bulunamadı. Önce ingest çalıştırın.",
            code="collection_missing",
        ) from exc

    if collection.count() == 0:
        raise VectorStoreError(
            "ChromaDB collection boş. Önce ingest çalıştırın.",
            code="collection_empty",
        )

    from backend.app.rag.embeddings import embed_query

    query_embedding = embed_query(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    if not results["ids"] or not results["ids"][0]:
        return []

    parsed: list[VectorSearchResult] = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
        strict=True,
    ):
        parsed.append(
            VectorSearchResult(
                text=doc or "",
                source=meta.get("source", ""),
                page=int(meta.get("page", 0)),
                score=_distance_to_score(dist),
                chunk_id=meta.get("chunk_id", ""),
                file_name=meta.get("file_name", ""),
                category=meta.get("category", ""),
                priority=meta.get("priority", ""),
                title=meta.get("title", ""),
                url=meta.get("url", ""),
                source_type=meta.get("source_type", ""),
            )
        )
    return parsed


def collection_chunk_count() -> int:
    try:
        return get_collection(create=False).count()
    except Exception:
        return 0


def is_vector_store_ready() -> bool:
    try:
        return collection_chunk_count() > 0
    except Exception:
        return False
