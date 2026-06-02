import json
from collections import defaultdict
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT, get_settings
from backend.app.rag.chunker import ChunkRecord, build_chunks_from_documents, normalize_chunk
from backend.app.rag.embeddings import EmbeddingError
from backend.app.rag.bm25_store import BM25StoreError, get_bm25_index_path, index_chunks_to_bm25
from backend.app.rag.vector_store import VectorStoreError, index_chunks_to_chroma
from backend.app.utils.document_loaders import load_documents_from_directories

RAW_PDF_DIR = PROJECT_ROOT / "data" / "raw" / "pdf"
RAW_WEB_DIR = PROJECT_ROOT / "data" / "raw" / "web"
RAW_SAMPLES_DIR = PROJECT_ROOT / "data" / "raw" / "samples"
DEFAULT_RAW_DIRS = [RAW_PDF_DIR, RAW_WEB_DIR, RAW_SAMPLES_DIR]

CHUNKS_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "chunks"
CHUNKS_OUTPUT_FILE = CHUNKS_OUTPUT_DIR / "chunks.jsonl"


class IngestError(Exception):
    """Ingestion pipeline hataları."""

    def __init__(self, message: str, code: str = "ingest_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def _resolve_output_path(output_path: Path | None) -> Path:
    return output_path if output_path is not None else CHUNKS_OUTPUT_FILE


def write_chunks_jsonl(chunks: list[ChunkRecord], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def load_chunks_jsonl(path: Path | None = None) -> list[ChunkRecord]:
    target = path or CHUNKS_OUTPUT_FILE
    if not target.exists():
        return []
    chunks: list[ChunkRecord] = []
    with target.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(normalize_chunk(json.loads(line)))
    return chunks


def summarize_sources(chunks: list[ChunkRecord] | None = None) -> list[dict]:
    """chunks.jsonl'den kaynak özeti üretir (/sources için)."""
    data = chunks if chunks is not None else load_chunks_jsonl()
    by_source: dict[str, dict] = defaultdict(
        lambda: {"name": "", "pages": set(), "chunks": 0, "source_type": ""}
    )
    for c in data:
        name = c["source"]
        by_source[name]["name"] = name
        by_source[name]["chunks"] += 1
        page = int(c.get("page", 0))
        if page > 0:
            by_source[name]["pages"].add(page)
        if not by_source[name]["source_type"]:
            by_source[name]["source_type"] = c.get("source_type", "")

    return [
        {
            "name": info["name"],
            "pages": len(info["pages"]),
            "chunks": info["chunks"],
            "source_type": info["source_type"],
        }
        for info in sorted(by_source.values(), key=lambda x: x["name"])
    ]


def run_document_ingestion(
    *,
    raw_dirs: list[Path] | None = None,
    output_path: Path | None = None,
) -> dict:
    """PDF, Markdown, metin ve JSON kaynaklarını chunks.jsonl'e dönüştürür."""
    settings = get_settings()
    dirs = raw_dirs if raw_dirs is not None else DEFAULT_RAW_DIRS
    out_path = _resolve_output_path(output_path)

    documents, file_counts = load_documents_from_directories(dirs)
    if not documents:
        searched = ", ".join(str(d) for d in dirs)
        raise IngestError(
            f"İşlenecek belge bulunamadı. Desteklenen formatlar: .pdf, .md, .txt, .json\n"
            f"Kontrol edilen klasörler: {searched}\n"
            f"Örnek belgeler için: {RAW_SAMPLES_DIR}",
            code="no_documents",
        )

    chunks = build_chunks_from_documents(documents)
    if not chunks:
        raise IngestError("Chunk oluşturulamadı.", code="no_chunks")

    write_chunks_jsonl(chunks, out_path)

    pages_with_number = sum(1 for d in documents if d.page > 0)

    return {
        "chunks_written": len(chunks),
        "documents_processed": len(documents),
        "pages_processed": pages_with_number,
        "files_by_type": file_counts,
        "output_path": str(out_path),
        "collection": settings.chroma_collection_name,
    }


def run_pdf_ingestion(
    *,
    pdf_dir: Path | None = None,
    output_path: Path | None = None,
) -> dict:
    """Geriye dönük uyumluluk — yalnızca PDF klasörü."""
    dirs = [pdf_dir or RAW_PDF_DIR, RAW_WEB_DIR, RAW_SAMPLES_DIR]
    return run_document_ingestion(raw_dirs=dirs, output_path=output_path)


def run_vector_indexing(
    *,
    rebuild: bool = True,
    chunks_path: Path | None = None,
) -> dict:
    target = _resolve_output_path(chunks_path)
    chunks = load_chunks_jsonl(target)
    if not chunks:
        raise IngestError(
            f"Chunk dosyası bulunamadı veya boş: {target}. Önce ingestion çalıştırın.",
            code="no_chunks_file",
        )

    try:
        vectors_indexed = index_chunks_to_chroma(chunks, rebuild=rebuild)
    except EmbeddingError as exc:
        raise IngestError(exc.message, code=exc.code) from exc
    except VectorStoreError as exc:
        raise IngestError(exc.message, code=exc.code) from exc

    return {
        "vectors_indexed": vectors_indexed,
        "collection": get_settings().chroma_collection_name,
    }


def run_bm25_indexing(
    *,
    rebuild: bool = True,
    chunks_path: Path | None = None,
) -> dict:
    target = _resolve_output_path(chunks_path)
    chunks = load_chunks_jsonl(target)
    if not chunks:
        raise IngestError(
            f"Chunk dosyası bulunamadı veya boş: {target}. Önce ingestion çalıştırın.",
            code="no_chunks_file",
        )

    try:
        bm25_indexed = index_chunks_to_bm25(chunks, rebuild=rebuild)
    except BM25StoreError as exc:
        raise IngestError(exc.message, code=exc.code) from exc

    return {
        "bm25_indexed": bm25_indexed,
        "index_path": get_bm25_index_path(),
    }


def run_ingestion(
    *,
    rebuild: bool = True,
    pdf_dir: Path | None = None,
    raw_dirs: list[Path] | None = None,
    output_path: Path | None = None,
    skip_pdf: bool = False,
    skip_sources: bool | None = None,
) -> dict:
    """
    Tam ingestion: kaynaklar → chunks.jsonl → ChromaDB + BM25.

    skip_sources / skip_pdf=True ise yalnızca mevcut chunks.jsonl indekslenir.
    """
    skip = skip_sources if skip_sources is not None else skip_pdf
    doc_result: dict | None = None

    if not skip:
        if raw_dirs is not None:
            doc_result = run_document_ingestion(raw_dirs=raw_dirs, output_path=output_path)
        else:
            dirs = [pdf_dir or RAW_PDF_DIR, RAW_WEB_DIR, RAW_SAMPLES_DIR]
            doc_result = run_document_ingestion(raw_dirs=dirs, output_path=output_path)

    vector_result = run_vector_indexing(rebuild=rebuild, chunks_path=output_path)
    bm25_result = run_bm25_indexing(rebuild=rebuild, chunks_path=output_path)

    chunks_count = (
        doc_result["chunks_written"] if doc_result else vector_result["vectors_indexed"]
    )

    files_by_type = doc_result.get("files_by_type", {}) if doc_result else {}

    return {
        "status": "success",
        "chunks_indexed": chunks_count,
        "vectors_indexed": vector_result["vectors_indexed"],
        "bm25_indexed": bm25_result["bm25_indexed"],
        "bm25_index_path": bm25_result["index_path"],
        "documents_processed": doc_result["documents_processed"] if doc_result else 0,
        "pages_processed": doc_result["pages_processed"] if doc_result else 0,
        "files_by_type": files_by_type,
        "output_path": doc_result["output_path"] if doc_result else str(_resolve_output_path(output_path)),
        "collection": vector_result["collection"],
        # geriye dönük alan adı
        "files_processed": sum(files_by_type.values()) if files_by_type else 0,
    }
