from openai import OpenAI

from backend.app.core.config import (
    ENV_FILE,
    get_settings,
    is_valid_openai_api_key,
    resolve_openai_api_key,
)

BATCH_SIZE = 100


class EmbeddingError(Exception):
    """OpenAI embedding hataları."""

    def __init__(self, message: str, code: str = "embedding_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def require_openai_api_key() -> str:
    key = resolve_openai_api_key()
    if not is_valid_openai_api_key(key):
        raise EmbeddingError(
            f"OPENAI_API_KEY tanımlı değil. "
            f"Lütfen şu dosyaya geçerli anahtarı ekleyin: {ENV_FILE}",
            code="missing_api_key",
        )
    return key


def get_openai_client() -> OpenAI:
    return OpenAI(api_key=require_openai_api_key())


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Metin listesini OpenAI embedding modeli ile vektörleştirir."""
    if not texts:
        return []

    settings = get_settings()
    client = get_openai_client()
    all_embeddings: list[list[float]] = []

    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        try:
            response = client.embeddings.create(
                model=settings.openai_embedding_model,
                input=batch,
            )
        except Exception as exc:
            raise EmbeddingError(
                f"OpenAI embedding isteği başarısız: {exc}",
                code="openai_embedding_failed",
            ) from exc

        ordered = sorted(response.data, key=lambda item: item.index)
        all_embeddings.extend(item.embedding for item in ordered)

    return all_embeddings


def embed_query(query: str) -> list[float]:
    """Tek sorgu metni için embedding döndürür."""
    vectors = embed_texts([query])
    return vectors[0]
