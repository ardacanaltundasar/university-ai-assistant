from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from backend.app.utils.text_cleaning import clean_text

# Dosya adı → okunabilir kaynak adı (context.md veri yapısı)
SOURCE_NAME_MAP: dict[str, str] = {
    "kayit_yonetmeligi": "Kayıt Yönetmeliği",
    "akademik_takvim": "Akademik Takvim",
    "sinav_yonetmeligi": "Sınav Yönetmeliği",
    "cap_yandal_yonetmeligi": "ÇAP / Yandal Yönetmeliği",
    "yaz_okulu_yonetmeligi": "Yaz Okulu Yönetmeliği",
}


@dataclass
class PdfPage:
    file_name: str
    source: str
    page: int
    text: str


def filename_to_source(file_name: str) -> str:
    stem = Path(file_name).stem.lower()
    if stem in SOURCE_NAME_MAP:
        return SOURCE_NAME_MAP[stem]
    return stem.replace("_", " ").title()


def load_pdf_pages(pdf_path: Path) -> list[PdfPage]:
    """Tek bir PDF'i sayfa sayfa okur; her sayfa için metadata korunur."""
    file_name = pdf_path.name
    source = filename_to_source(file_name)
    reader = PdfReader(str(pdf_path))
    pages: list[PdfPage] = []

    for page_num, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        text = clean_text(raw)
        if not text:
            continue
        pages.append(
            PdfPage(
                file_name=file_name,
                source=source,
                page=page_num,
                text=text,
            )
        )

    return pages


def load_pdfs_from_directory(pdf_dir: Path) -> list[PdfPage]:
    """Klasördeki tüm PDF dosyalarını sırayla okur."""
    if not pdf_dir.exists():
        return []

    all_pages: list[PdfPage] = []
    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        all_pages.extend(load_pdf_pages(pdf_path))
    return all_pages
