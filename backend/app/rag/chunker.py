from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from backend.app.utils.pdf_loader import PdfPage
from backend.app.utils.source_document import SourceDocument

DEFAULT_CHUNK_SIZE = 3500
DEFAULT_CHUNK_OVERLAP = 500
DEFAULT_CATEGORY = "Genel"
DEFAULT_PRIORITY = "static"


class ChunkRecord(TypedDict, total=False):
    chunk_id: str
    text: str
    source: str
    file_name: str
    page: int
    category: str
    priority: str
    source_type: str
    title: str
    content_type: str
    section_title: str
    indexed_at: str
    url: str
    date: str


def _indexed_at_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_chunk(raw: dict) -> ChunkRecord:
    """Eski chunks.jsonl kayıtlarını yeni metadata şemasına uyumlar."""
    return ChunkRecord(
        chunk_id=raw["chunk_id"],
        text=raw["text"],
        source=raw["source"],
        file_name=raw.get("file_name", ""),
        page=int(raw.get("page", 0)),
        category=raw.get("category", DEFAULT_CATEGORY),
        priority=raw.get("priority", DEFAULT_PRIORITY),
        source_type=raw.get("source_type", "pdf"),
        title=raw.get("title", raw.get("source", "")),
        content_type=raw.get("content_type", "pdf"),
        section_title=raw.get("section_title", ""),
        indexed_at=raw.get("indexed_at", _indexed_at_iso()),
        url=raw.get("url", ""),
        date=raw.get("date", ""),
    )


def _find_break_index(text: str, start: int, end: int) -> int:
    for sep in ("\n\n", ". ", " "):
        idx = text.rfind(sep, start, end)
        if idx > start:
            return idx + len(sep)
    return end


def split_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            end = _find_break_index(text, start, end)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)

    return chunks


def _make_chunk_record(
    *,
    chunk_id: str,
    text: str,
    doc: SourceDocument,
    category: str,
    priority: str,
    indexed_at: str,
) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        text=text,
        source=doc.source,
        file_name=doc.file_name,
        page=doc.page,
        category=category,
        priority=priority,
        source_type=doc.source_type,
        title=doc.title,
        content_type=doc.content_type,
        section_title=doc.section_title,
        indexed_at=indexed_at,
        url=doc.url,
        date=doc.date,
    )


def build_chunks_from_documents(
    documents: list[SourceDocument],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    category: str = DEFAULT_CATEGORY,
    priority: str = DEFAULT_PRIORITY,
) -> list[ChunkRecord]:
    """PDF, Markdown ve diğer kaynaklardan standart metadata ile chunk üretir."""
    records: list[ChunkRecord] = []
    indexed_at = _indexed_at_iso()
    seen_chunk_ids: set[str] = set()

    for doc in documents:
        stem = Path(doc.file_name).stem if doc.file_name else "doc"
        parts = split_text(doc.text, chunk_size=chunk_size, overlap=overlap)

        if doc.page > 0:
            id_prefix = f"{stem}_p{doc.page}"
        elif doc.section_title:
            safe_section = re.sub(r"[^\w]+", "_", doc.section_title.lower())[:40].strip("_")
            id_prefix = f"{stem}_s{safe_section or 'sec'}"
        else:
            id_prefix = stem

        for idx, part in enumerate(parts, start=1):
            chunk_id = f"{id_prefix}_c{idx}"
            if chunk_id in seen_chunk_ids:
                suffix = 2
                while f"{chunk_id}_{suffix}" in seen_chunk_ids:
                    suffix += 1
                chunk_id = f"{chunk_id}_{suffix}"
            seen_chunk_ids.add(chunk_id)
            records.append(
                _make_chunk_record(
                    chunk_id=chunk_id,
                    text=part,
                    doc=doc,
                    category=category,
                    priority=priority,
                    indexed_at=indexed_at,
                )
            )

    return records


def build_chunks_from_pages(
    pages: list[PdfPage],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
    category: str = DEFAULT_CATEGORY,
    priority: str = DEFAULT_PRIORITY,
) -> list[ChunkRecord]:
    documents = [
        SourceDocument(
            file_name=p.file_name,
            source=p.source,
            source_type="pdf",
            title=p.source,
            content_type="pdf",
            text=p.text,
            page=p.page,
            section_title="",
        )
        for p in pages
    ]
    return build_chunks_from_documents(
        documents,
        chunk_size=chunk_size,
        overlap=overlap,
        category=category,
        priority=priority,
    )


def split_page_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    return split_text(text, chunk_size=chunk_size, overlap=overlap)
