"""Kaynak belge — PDF, Markdown, metin ve JSON için ortak model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SourceDocument:
    """Ingestion pipeline'ında işlenen tek bir belge parçası (sayfa veya bölüm)."""

    file_name: str
    source: str
    source_type: str
    title: str
    content_type: str
    text: str
    page: int = 0
    section_title: str = ""
    file_path: str = ""
    url: str = ""
    date: str = ""
