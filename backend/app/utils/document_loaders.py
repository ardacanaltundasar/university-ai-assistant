"""PDF, Markdown, düz metin ve JSON kaynaklarını yükler."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.utils.markdown_loader import load_markdown_from_directory
from backend.app.utils.pdf_loader import load_pdfs_from_directory
from backend.app.utils.source_document import SourceDocument
from backend.app.utils.text_cleaning import clean_text

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt", ".json"}

MIN_WEB_JSON_CONTENT_CHARS = 30


def _pdf_pages_to_documents(pdf_dir: Path) -> list[SourceDocument]:
    from backend.app.utils.pdf_loader import PdfPage

    pages = load_pdfs_from_directory(pdf_dir)
    docs: list[SourceDocument] = []
    for page in pages:
        docs.append(
            SourceDocument(
                file_name=page.file_name,
                source=page.source,
                source_type="pdf",
                title=page.source,
                content_type="pdf",
                text=page.text,
                page=page.page,
                section_title="",
                file_path=str(pdf_dir / page.file_name),
            )
        )
    return docs


def _load_text_files(directory: Path) -> list[SourceDocument]:
    if not directory.exists():
        return []
    documents: list[SourceDocument] = []
    for txt_path in sorted(directory.glob("*.txt")):
        text = clean_text(txt_path.read_text(encoding="utf-8"))
        if not text:
            continue
        stem = txt_path.stem
        title = stem.replace("_", " ").title()
        documents.append(
            SourceDocument(
                file_name=txt_path.name,
                source=title,
                source_type="text",
                title=title,
                content_type="web",
                text=text,
                page=0,
                section_title="",
                file_path=str(txt_path),
            )
        )
    return documents


def _web_json_to_document(json_path: Path, item: dict) -> SourceDocument | None:
    """Crawler çıktısı: tek kayıt {title, url, content, source_type, content_type, ...}."""
    title = str(item.get("title") or item.get("name") or json_path.stem)
    body = str(item.get("content") or item.get("body") or item.get("text") or "")
    body = clean_text(body)
    if len(body) < MIN_WEB_JSON_CONTENT_CHARS:
        return None

    url = str(item.get("url") or "").strip()
    date_raw = item.get("date")
    date = "" if date_raw is None else str(date_raw).strip()
    source_type = str(item.get("source_type") or "web")
    content_type = str(item.get("content_type") or "web_page")
    return SourceDocument(
        file_name=json_path.name,
        source=str(json_path),
        source_type=source_type,
        title=title,
        content_type=content_type,
        text=body,
        page=0,
        section_title=title,
        file_path=str(json_path),
        url=url,
        date=date,
    )


def _load_json_files(directory: Path) -> list[SourceDocument]:
    """JSON: web crawler tek kayıt, liste veya {items: [...]} formatı."""
    if not directory.exists():
        return []
    documents: list[SourceDocument] = []

    for json_path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        if isinstance(payload, dict) and (
            payload.get("source_type") == "web"
            or ("content" in payload and "url" in payload)
        ):
            doc = _web_json_to_document(json_path, payload)
            if doc:
                documents.append(doc)
            continue

        items: list = []
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get("items") or payload.get("announcements") or []

        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or f"Duyuru {idx}")
            body = str(item.get("body") or item.get("content") or item.get("text") or "")
            body = clean_text(body)
            if not body:
                continue
            documents.append(
                SourceDocument(
                    file_name=json_path.name,
                    source=title,
                    source_type="json",
                    title=title,
                    content_type="announcement",
                    text=body,
                    page=0,
                    section_title=title,
                    file_path=str(json_path),
                )
            )

    return documents


def load_documents_from_directories(
    directories: list[Path],
) -> tuple[list[SourceDocument], dict[str, int]]:
    """
    Verilen klasörlerdeki desteklenen dosyaları yükler.
    Dönüş: (belgeler, {kaynak_türü: dosya_sayısı})
    """
    all_docs: list[SourceDocument] = []
    counts: dict[str, int] = {
        "pdf": 0,
        "markdown": 0,
        "text": 0,
        "json": 0,
    }

    for directory in directories:
        if not directory.exists():
            continue

        pdf_files = list(directory.glob("*.pdf"))
        if pdf_files:
            counts["pdf"] += len(pdf_files)
            all_docs.extend(_pdf_pages_to_documents(directory))

        md_files = list(directory.glob("*.md"))
        if md_files:
            counts["markdown"] += len(md_files)
            all_docs.extend(load_markdown_from_directory(directory))

        txt_files = list(directory.glob("*.txt"))
        if txt_files:
            counts["text"] += len(txt_files)
            all_docs.extend(_load_text_files(directory))

        json_files = [f for f in directory.glob("*.json") if f.name != "gold_faq.json"]
        if json_files:
            counts["json"] += len(json_files)
            all_docs.extend(_load_json_files(directory))

    return all_docs, counts
