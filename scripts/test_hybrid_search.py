"""Hybrid search test scripti.

Çalıştırma (proje kökünden):
    export PYTHONPATH=.
    python scripts/test_hybrid_search.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import load_env  # noqa: E402

load_env(reload_settings=True)

from backend.app.rag.hybrid_search import hybrid_search  # noqa: E402

TEST_QUERIES = [
    "tek ders sınavına kimler girebilir?",
    "ÇAP için ortalama şartı nedir?",
    "transkript nasıl alınır?",
    "harç ödemesi nasıl yapılır?",
]


def _preview(text: str, limit: int = 120) -> str:
    one_line = text.replace("\n", " ").strip()
    if len(one_line) <= limit:
        return one_line
    return one_line[:limit] + "…"


def run_query(query: str) -> None:
    print("=" * 60)
    print(f"Sorgu: {query}")
    results = hybrid_search(query, top_k=5)
    if not results:
        print("Sonuç bulunamadı.\n")
        return
    for i, hit in enumerate(results, start=1):
        print(
            f"  {i}. [{hit['retrieval_method']}] skor={hit['score']:.3f} | "
            f"{hit['source']} s.{hit['page']} | {hit['chunk_id']}"
        )
        print(f"     {_preview(hit['text'])}")
    print()


def main() -> None:
    for q in TEST_QUERIES:
        run_query(q)


if __name__ == "__main__":
    main()
