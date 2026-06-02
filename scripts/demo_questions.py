"""Örnek soru seti — agent akışını terminalde doğrular.

Çalıştırma (proje kökünden):
    export PYTHONPATH=.
    python scripts/demo_questions.py

Not: Anlamlı retrieval için önce ingestion yapılmış olmalı:
    python scripts/ingest_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import load_env  # noqa: E402

load_env(reload_settings=True)

from backend.app.agent.graph import run_agent  # noqa: E402
from backend.app.agent.scope import is_out_of_scope  # noqa: E402

DEMO_QUESTIONS = [
    "Kayıt dondurma şartları nelerdir?",
    "Tek ders sınavına kimler girebilir?",
    "Yaz okulunda en fazla kaç kredi alabilirim?",
    "ÇAP yapmak için not ortalamam kaç olmalı?",
    "Transkriptimi nereden alabilirim?",
    "OBS şifremi unuttum, ne yapmalıyım?",
    "Kampüs kartımı kaybettim, ne yapmalıyım?",
    "Mazeret sınavı için sağlık raporu yeterli mi?",
    "Danışman onayı olmadan ders seçimi tamamlanır mı?",
    "Harç ödemesini nasıl yapabilirim?",
    "Bugün hava nasıl?",
    "Bana gerçek transkriptimi çıkarır mısın?",
]

SAFE_PHRASES = (
    "yeterli bilgi",
    "kesin cevap veremiyorum",
    "iletişime geç",
    "doğrulanmış kaynak",
)


def _preview(text: str, limit: int = 160) -> str:
    line = text.replace("\n", " ").strip()
    return line if len(line) <= limit else line[:limit] + "…"


def evaluate(question: str, response) -> tuple[bool, str]:
    answer = response.answer or ""
    confidence = response.confidence
    citations = response.citations or []
    off_topic = is_out_of_scope(question)[0]

    if not answer.strip():
        return False, "Boş cevap"

    if off_topic:
        if confidence in ("high", "medium") and citations:
            return False, "Kapsam dışı soruda yüksek güven + citation olmamalı"
        if not any(p in answer.lower() for p in SAFE_PHRASES):
            return False, "Kapsam dışı soruda güvenli mesaj bekleniyor"
        return True, "Kapsam dışı — güvenli yanıt"

    if confidence in ("high", "medium") and not citations:
        return False, "high/medium için citation gerekli"

    return True, "OK"


def main() -> None:
    print("Medeniyet Üniversitesi AI Asistanı — Örnek Soru Doğrulaması\n" + "=" * 60)
    passed = 0
    failed = 0

    for i, question in enumerate(DEMO_QUESTIONS, start=1):
        print(f"\n[{i}/{len(DEMO_QUESTIONS)}] Question: {question}")
        try:
            response = run_agent(question)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            print("  Result: FAIL")
            failed += 1
            continue

        ok, reason = evaluate(question, response)
        print(f"  Answer preview: {_preview(response.answer)}")
        print(f"  Confidence: {response.confidence}")
        print(f"  Citations: {len(response.citations)}")
        print(f"  Steps ({len(response.steps)}):")
        for step in response.steps[:6]:
            print(f"    - {step}")
        if len(response.steps) > 6:
            print(f"    ... +{len(response.steps) - 6} adım")

        status = "PASS" if ok else "FAIL"
        print(f"  Result: {status} ({reason})")
        if ok:
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"Özet: {passed} PASS, {failed} FAIL / {len(DEMO_QUESTIONS)} soru")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
