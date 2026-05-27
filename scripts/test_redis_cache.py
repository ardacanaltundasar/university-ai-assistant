"""Redis answer cache birim testleri — Redis olmadan normalize/key mantığı."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.cache.redis_cache import (  # noqa: E402
    build_answer_cache_key,
    normalize_question,
)


def test_normalize_question() -> None:
    assert normalize_question("  Kayıt   Dondurma  ") == "kayıt dondurma"
    assert normalize_question("İstanbul") == "i̇stanbul" or normalize_question("İstanbul") == "istanbul"
    assert normalize_question("  ") == ""


def test_build_answer_cache_key() -> None:
    key1 = build_answer_cache_key("Kayıt dondurma?", intent="rag_question")
    key2 = build_answer_cache_key("kayıt dondurma?", intent="rag_question")
    key3 = build_answer_cache_key("Kayıt dondurma?", intent="resource_recommendation")

    assert key1 == key2
    assert key1.startswith("answer_cache:rag_question:")
    assert key3 != key1
    assert len(key1) < 80


if __name__ == "__main__":
    test_normalize_question()
    test_build_answer_cache_key()
    print("OK — redis cache unit checks passed")
