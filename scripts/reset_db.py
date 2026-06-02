"""ChromaDB ve BM25 indekslerini sıfırlar.

Çalıştırma (proje kökünden):
    python scripts/reset_db.py
"""


def main() -> None:
    print(
        "Manuel indeks sıfırlama:\n"
        "  1. data/chroma/, data/bm25/ ve data/processed/ dizinlerini silin\n"
        "  2. python scripts/ingest_data.py çalıştırın"
    )


if __name__ == "__main__":
    main()
