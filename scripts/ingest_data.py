"""Belge ingestion: PDF, Markdown, metin, JSON → chunks.jsonl → Chroma + BM25.

Çalıştırma (proje kökünden):
    export PYTHONPATH=.
    python scripts/ingest_data.py

    # Yalnızca mevcut chunks.jsonl → Chroma + BM25 (kaynak adımını atla)
    python scripts/ingest_data.py --skip-sources
"""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import (  # noqa: E402
    ENV_FILE,
    is_valid_openai_api_key,
    load_env,
    resolve_openai_api_key,
)
from backend.app.rag.ingest import (  # noqa: E402
    RAW_PDF_DIR,
    RAW_SAMPLES_DIR,
    RAW_WEB_DIR,
    IngestError,
    run_ingestion,
)

load_env(reload_settings=True)


def _include_sample_data_enabled() -> bool:
    """INCLUDE_SAMPLE_DATA — yoksa true (hızlı başlangıç)."""
    raw = os.getenv("INCLUDE_SAMPLE_DATA", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _build_raw_dirs(*, pdf_dir: Path | None, include_samples: bool) -> list[Path]:
    dirs = [pdf_dir or RAW_PDF_DIR, RAW_WEB_DIR]
    if include_samples:
        dirs.append(RAW_SAMPLES_DIR)
    return dirs


def _resolve_raw_dirs(args: argparse.Namespace) -> list[Path]:
    if args.samples_only:
        print("Sample data ingestion enabled (--samples-only)")
        return [RAW_SAMPLES_DIR]

    include_samples = _include_sample_data_enabled()
    if include_samples:
        print("Sample data ingestion enabled")
    else:
        print("Sample data ingestion disabled, skipping data/raw/samples")

    return _build_raw_dirs(pdf_dir=args.pdf_dir, include_samples=include_samples)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "data/raw altındaki PDF, Markdown, metin ve JSON dosyalarını işler; "
            "chunks.jsonl, ChromaDB ve BM25 index oluşturur."
        )
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=None,
        help="PDF klasörü (varsayılan: data/raw/pdf; diğer raw klasörleri de taranır)",
    )
    parser.add_argument(
        "--skip-sources",
        "--skip-pdf",
        dest="skip_sources",
        action="store_true",
        help="Kaynak okumayı atla; mevcut chunks.jsonl ile Chroma + BM25 indeksle",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Mevcut Chroma/BM25 indekslerini silmeden yeniden oluştur (varsayılan: rebuild)",
    )
    parser.add_argument(
        "--samples-only",
        action="store_true",
        help="Yalnızca data/raw/samples klasörünü işle (örnek belgeler)",
    )
    args = parser.parse_args()

    api_key = resolve_openai_api_key()
    if not is_valid_openai_api_key(api_key):
        print(
            f"Hata: OPENAI_API_KEY geçerli değil.\n"
            f"  Dosya: {ENV_FILE}\n"
            f"  Dosya mevcut: {ENV_FILE.is_file()}\n"
            "  OPENAI_API_KEY satırı 'sk-' ile başlamalı.",
            file=sys.stderr,
        )
        sys.exit(1)

    raw_dirs = None if args.skip_sources else _resolve_raw_dirs(args)

    try:
        result = run_ingestion(
            rebuild=not args.no_rebuild,
            pdf_dir=args.pdf_dir,
            raw_dirs=raw_dirs,
            skip_sources=args.skip_sources,
        )
        print("Ingestion tamamlandı.")
        if not args.skip_sources:
            by_type = result.get("files_by_type", {})
            if by_type:
                print("  Dosya sayıları:")
                for kind, count in by_type.items():
                    if count:
                        print(f"    {kind}: {count}")
            print(f"  İşlenen belge parçası: {result.get('documents_processed', 0)}")
            print(f"  Sayfa (PDF): {result.get('pages_processed', 0)}")
        print(f"  Chunk (jsonl): {result['chunks_indexed']}")
        print(f"  Vektör (Chroma): {result['vectors_indexed']}")
        print(f"  BM25 index    : {result['bm25_indexed']} chunk")
        print(f"  BM25 dosya    : {result['bm25_index_path']}")
        print(f"  Collection    : {result['collection']}")
        print(f"  Çıktı (jsonl) : {result['output_path']}")
    except IngestError as exc:
        print(f"Hata: {exc.message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
