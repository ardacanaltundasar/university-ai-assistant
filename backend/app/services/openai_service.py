import json
import logging
import re

from openai import OpenAI

from backend.app.core.config import (
    ENV_FILE,
    get_settings,
    is_valid_openai_api_key,
    resolve_openai_api_key,
)

logger = logging.getLogger(__name__)


class OpenAIServiceError(Exception):
    def __init__(self, message: str, code: str = "openai_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def require_api_key() -> str:
    key = resolve_openai_api_key()
    if not is_valid_openai_api_key(key):
        raise OpenAIServiceError(
            f"OPENAI_API_KEY tanımlı değil. "
            f"Lütfen şu dosyaya geçerli anahtarı ekleyin: {ENV_FILE}",
            code="missing_api_key",
        )
    return key


def get_client() -> OpenAI:
    return OpenAI(api_key=require_api_key())


def parse_json_response(text: str) -> dict | None:
    """LLM çıktısından JSON çıkarır; hata durumunda None döner."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
    return None


def chat_completion(
    *,
    system: str,
    user: str,
    temperature: float = 0.2,
    max_tokens: int = 1500,
) -> str | None:
    """GPT ile serbest metin cevap üretir."""
    settings = get_settings()
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
    except OpenAIServiceError as exc:
        logger.warning("OpenAI kullanılamıyor: %s", exc.message)
        return None
    except Exception as exc:
        logger.warning("OpenAI chat_completion hatası: %s", exc)
        return None


def chat_json(
    *,
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: int = 800,
) -> dict | None:
    """GPT-4o mini ile JSON yanıt ister; parse edilmiş dict döner."""
    settings = get_settings()
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        return parse_json_response(content)
    except OpenAIServiceError as exc:
        logger.warning("OpenAI kullanılamıyor: %s", exc.message)
        return None
    except Exception as exc:
        logger.warning("OpenAI chat_json hatası: %s", exc)
        return None
