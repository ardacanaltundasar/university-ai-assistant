"""Redis answer cache birim testleri — Redis olmadan normalize/key mantığı."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.cache.redis_cache import (  # noqa: E402
    build_answer_cache_key,
    is_question_cache_eligible,
    normalize_question,
    normalize_question_for_cache,
)


def test_normalize_question() -> None:
    assert normalize_question("  Kayıt   Dondurma  ") == "kayıt dondurma"
    assert normalize_question("İstanbul") == "i̇stanbul" or normalize_question("İstanbul") == "istanbul"
    assert normalize_question("  ") == ""
    assert (
        normalize_question_for_cache("Ders seçimi nasıl yapılır?")
        == "ders seçimi nasıl yapılır"
    )
    assert (
        normalize_question_for_cache("  Ders seçimi   nasıl yapılır . ")
        == "ders seçimi nasıl yapılır"
    )
    assert normalize_question_for_cache(None) == ""


def test_build_answer_cache_key() -> None:
    key1 = build_answer_cache_key("Kayıt dondurma?", intent="rag_question")
    key2 = build_answer_cache_key("kayıt dondurma?", intent="rag_question")
    key3 = build_answer_cache_key("Kayıt dondurma?", intent="resource_recommendation")
    key4 = build_answer_cache_key("Ders seçimi nasıl yapılır?", intent="process_guidance")
    key5 = build_answer_cache_key("ders seçimi nasıl yapılır.", intent="process_guidance")

    assert key1 == key2
    assert key4 == key5
    assert key1.startswith("answer_cache:rag_question:")
    assert key3 != key1
    assert len(key1) < 80


def test_cache_bypass() -> None:
    assert is_question_cache_eligible("Kayıt dondurma şartları nelerdir?")
    assert not is_question_cache_eligible(
        "Adım Ahmet, öğrenci numaram 12345, dilekçe hazırla"
    )
    assert not is_question_cache_eligible("Dilekçe yaz bana")


if __name__ == "__main__":
    test_normalize_question()
    test_build_answer_cache_key()
    test_cache_bypass()
    print("OK — redis cache unit checks passed")
