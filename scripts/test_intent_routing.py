"""Intent routing smoke test (keyword rules, LLM kapalı).

    export PYTHONPATH=.
    python scripts/test_intent_routing.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agent.intent import classify_intent  # noqa: E402

CASES: list[tuple[str, str]] = [
    ("Veri yapıları için kaynak öner.", "resource_recommendation"),
    ("Algoritma dersi için kitap öner.", "resource_recommendation"),
    ("Bu ders içeriğine göre ne çalışmalıyım?", "resource_recommendation"),
    ("Kayıt dondurma şartları nelerdir?", "rag_question"),
    ("Mazeret sınavına kimler başvurabilir?", "rag_question"),
    ("Ders seçimi nasıl yapılır?", "process_guidance"),
    ("Harç ödeme işlemleri nasıl yapılır?", "process_guidance"),
    ("Yatay geçiş için ne yapmam gerekiyor?", "process_guidance"),
    ("Kayıt dondurma süreci nasıl ilerler?", "process_guidance"),
    ("Ders kayıt süreci nasıl işler?", "process_guidance"),
    ("Kayıt dondurma dilekçesi hazırla", "petition_generation"),
]


def main() -> None:
    ok = 0
    for question, expected in CASES:
        intent, reason = classify_intent(question, use_llm=False)
        status = "OK" if intent == expected else "FAIL"
        if intent == expected:
            ok += 1
        print(f"{status}  {question[:50]:50} → {intent} (beklenen: {expected})")
        if status == "FAIL":
            print(f"       {reason}")
    print(f"\n{ok}/{len(CASES)} geçti")
    sys.exit(0 if ok == len(CASES) else 1)


if __name__ == "__main__":
    main()
