"""Markdown dosyalarını başlık/bölüm metadata'sı ile yükler."""

from __future__ import annotations

import re
from pathlib import Path

from backend.app.utils.source_document import SourceDocument
from backend.app.utils.text_cleaning import clean_text

CONTENT_TYPE_BY_STEM: dict[str, str] = {
    "sample_regulation": "regulation",
    "sample_academic_calendar": "calendar",
    "sample_announcement": "announcement",
}

SOURCE_TYPE_MARKDOWN = "markdown"


def _stem_to_title(stem: str) -> str:
    if stem.startswith("sample_"):
        stem = stem[len("sample_") :]
    return stem.replace("_", " ").title()


def _infer_content_type(stem: str) -> str:
    return CONTENT_TYPE_BY_STEM.get(stem, "sample")


def _extract_document_title(content: str, *, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("# ").strip()
    return fallback


def _split_markdown_sections(content: str) -> list[tuple[str, str]]:
    """
    ## ve ### başlıklarına göre böler.
    Dönüş: (section_title, section_body) — başlık satırı gövdede korunur.
    """
    content = content.strip()
    if not content:
        return []

    pattern = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(content))

    if not matches:
        return [("", content)]

    sections: list[tuple[str, str]] = []
    preamble = content[: matches[0].start()].strip()
    if preamble:
        sections.append(("", preamble))

    for i, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        if body:
            sections.append((title, body))

    return sections


def load_markdown_file(md_path: Path) -> list[SourceDocument]:
    """Tek Markdown dosyasını bölümlere ayırarak SourceDocument listesi döner."""
    file_name = md_path.name
    stem = md_path.stem
    raw = md_path.read_text(encoding="utf-8")
    cleaned = clean_text(raw)
    if not cleaned:
        return []

    title = _extract_document_title(cleaned, fallback=_stem_to_title(stem))
    source = title
    content_type = _infer_content_type(stem)
    rel_path = str(md_path)

    sections = _split_markdown_sections(cleaned)
    documents: list[SourceDocument] = []

    for section_title, body in sections:
        text = body.strip()
        if not text:
            continue
        documents.append(
            SourceDocument(
                file_name=file_name,
                source=source,
                source_type=SOURCE_TYPE_MARKDOWN,
                title=title,
                content_type=content_type,
                text=text,
                page=0,
                section_title=section_title,
                file_path=rel_path,
            )
        )

    return documents


def load_markdown_from_directory(directory: Path) -> list[SourceDocument]:
    if not directory.exists():
        return []
    documents: list[SourceDocument] = []
    for md_path in sorted(directory.glob("*.md")):
        documents.extend(load_markdown_file(md_path))
    return documents
