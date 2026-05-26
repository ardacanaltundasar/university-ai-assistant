"""BM25 keyword search test scripti.

Çalıştırma (proje kökünden):
    export PYTHONPATH=.
    python scripts/test_bm25_search.py
    python scripts/test_bm25_search.py "tek ders sınavı"
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import load_env  # noqa: E402

load_env(reload_settings=True)

from backend.app.rag.bm25_store import BM25StoreError, bm25_search  # noqa: E402

DEFAULT_QUERY = "tek ders sınavı"


def main() -> None:
    parser = argparse.ArgumentParser(description="BM25 keyword search testi")
    parser.add_argument("query", nargs="?", default=DEFAULT_QUERY, help="Arama sorgusu")
    parser.add_argument("-k", type=int, default=5, help="Top-k sonuç (varsayılan: 5)")
    args = parser.parse_args()

    print(f"Sorgu: {args.query}\n")

    try:
        results = bm25_search(args.query, top_k=args.k)
    except BM25StoreError as exc:
        print(f"Hata: {exc.message}", file=sys.stderr)
        sys.exit(1)

    if not results:
        print("Sonuç bulunamadı.")
        return

    for i, hit in enumerate(results, start=1):
        preview = hit["text"][:200].replace("\n", " ")
        if len(hit["text"]) > 200:
            preview += "…"
        print(f"--- Sonuç {i} (skor: {hit['score']:.3f}) ---")
        print(f"Kaynak : {hit['source']} | Sayfa: {hit['page']} | chunk_id: {hit['chunk_id']}")
        print(f"Önizleme: {preview}\n")


if __name__ == "__main__":
    main()
