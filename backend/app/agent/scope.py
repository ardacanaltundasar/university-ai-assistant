"""Soru kapsamı kontrolü — canlı sistem / kişisel veri / alakasız sorular."""

from __future__ import annotations

# (alt string listesi, kısa açıklama)
OUT_OF_SCOPE_RULES: list[tuple[str, str]] = [
    ("hava nasıl", "Genel bilgi — kaynak kapsamı dışı"),
    ("hava kaç derece", "Genel bilgi — kaynak kapsamı dışı"),
    ("gerçek transkriptimi çıkar", "Kişisel belge üretimi"),
    ("gerçek transkriptimi çıkarır", "Kişisel belge üretimi"),
    ("bana gerçek transkript", "Kişisel belge üretimi"),
    ("şifremi değiştir", "Canlı sistem işlemi"),
    ("şifremi sıfırla bana", "Canlı sistem işlemi"),
    ("borcum ne kadar", "Kişisel finansal veri"),
    ("harç borcum ne", "Kişisel finansal veri"),
    ("benim not ortalamam", "Kişisel akademik veri"),
    ("benim transkriptim", "Kişisel akademik veri"),
    ("kaç borcum var", "Kişisel finansal veri"),
]


def is_out_of_scope(question: str) -> tuple[bool, str]:
    """
    PoC kapsamı dışı soruları tespit eder.
    'OBS şifremi unuttum ne yapmalıyım?' gibi genel yönlendirme soruları kapsam içindedir.
    """
    q = question.lower().strip()
    if not q:
        return True, "Boş soru"

    for phrase, reason in OUT_OF_SCOPE_RULES:
        if phrase in q:
            return True, reason

    if "gerçek" in q and "transkript" in q and any(
        w in q for w in ("çıkar", "üret", "gönder", "yapar mısın", "yapar misin")
    ):
        return True, "Kişisel belge üretimi"

    if "benim" in q and any(w in q for w in ("not ortalam", "borcum", "transkriptim")):
        return True, "Kişisel veri sorgusu"

    return False, ""
