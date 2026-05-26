import re


def clean_text(text: str) -> str:
    """PDF çıktısındaki fazla boşluk ve satır sonlarını düzenler."""
    if not text:
        return ""

    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"-\n(?=\w)", "", text)  # satır sonu tire birleştirme
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
