import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py → proje kökü (uni-agent-project)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


def load_env(*, reload_settings: bool = False) -> Path:
    """
    Proje kökündeki .env dosyasını yükler.
    scripts/ veya farklı cwd'den çalıştırılsa da aynı dosya okunur.
    """
    if ENV_FILE.is_file():
        # Proje .env dosyası, shell'deki boş/yanlış değişkenlerin üzerine yazar
        load_dotenv(ENV_FILE, override=True)
    else:
        load_dotenv(override=False)

    if reload_settings:
        get_settings.cache_clear()

    return ENV_FILE


# Modül import edildiğinde bir kez yükle
load_env()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    chroma_persist_dir: str = "./data/chroma"
    chroma_collection_name: str = "university_agent_collection"
    bm25_index_path: str = "./data/bm25/bm25_index.pkl"

    redis_url: str = "redis://localhost:6379/0"
    enable_redis_cache: bool = True
    redis_cache_ttl_seconds: int = 3600

    enable_agent_self_check: bool = True
    max_retrieval_retries: int = 1

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    debug_retrieval: bool = False

    postgres_user: str = "uni_agent"
    postgres_password: str = "change-me"
    postgres_db: str = "uni_agent_db"
    database_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _read_var_from_env_file(var_name: str) -> str:
    """Proje .env dosyasından doğrudan okur (yorum satırlarını atlar)."""
    if not ENV_FILE.is_file():
        return ""
    try:
        content = ENV_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""

    value = ""
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not stripped.startswith(f"{var_name}="):
            continue
        value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return value


def resolve_openai_api_key() -> str:
    """
    OPENAI_API_KEY: önce .env dosyasından, sonra dotenv/settings.
    Placeholder (your_...) değerleri yok sayılır.
    """
    key = _read_var_from_env_file("OPENAI_API_KEY")
    if key and not key.startswith("your_"):
        return key

    load_env(reload_settings=True)
    settings = get_settings()
    key = settings.openai_api_key.strip()
    if not key or key.startswith("your_"):
        key = os.getenv("OPENAI_API_KEY", "").strip()
    if key.startswith("your_"):
        return ""
    return key


def is_valid_openai_api_key(key: str) -> bool:
    return bool(key) and not key.startswith("your_")


def require_openai_api_key() -> str:
    """API anahtarı zorunlu; yoksa ValueError."""
    key = resolve_openai_api_key()
    if not is_valid_openai_api_key(key):
        raise ValueError(
            f"OPENAI_API_KEY tanımlı değil veya placeholder. "
            f"Dosyayı kaydedin: {ENV_FILE}"
        )
    return key


def _resolve_project_path(relative: str) -> Path:
    path = Path(relative)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def chroma_path(settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    return _resolve_project_path(s.chroma_persist_dir)


def bm25_path(settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    return _resolve_project_path(s.bm25_index_path)


def is_debug_retrieval_enabled() -> bool:
    return get_settings().debug_retrieval


def get_database_url() -> str:
    """PostgreSQL bağlantı URL'si (.env → DATABASE_URL)."""
    explicit = _read_var_from_env_file("DATABASE_URL")
    if explicit:
        return explicit.strip()

    settings = get_settings()
    if settings.database_url.strip():
        return settings.database_url.strip()

    user = _read_var_from_env_file("POSTGRES_USER") or settings.postgres_user
    password = _read_var_from_env_file("POSTGRES_PASSWORD") or settings.postgres_password
    db_name = _read_var_from_env_file("POSTGRES_DB") or settings.postgres_db
    if user and password and db_name:
        host = os.getenv("POSTGRES_HOST", "localhost")
        return f"postgresql+psycopg2://{user}:{password}@{host}:5432/{db_name}"
    return ""
