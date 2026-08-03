"""
Central application configuration.

Everything that changes between local / staging / production lives here and is
read from environment variables. Nothing secret is ever hard-coded.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/  -> two levels up from app/core/config.py
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "AI Financial Document Parser"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # --- Database (MongoDB) ---
    # Local:      mongodb://localhost:27017
    # Production: mongodb+srv://<user>:<pass>@cluster.mongodb.net/?retryWrites=true&w=majority
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "findoc"

    # --- JWT ---
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # --- File upload ---
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    REPORT_DIR: Path = BASE_DIR / "reports"
    MAX_UPLOAD_SIZE_MB: int = 25
    ALLOWED_EXTENSIONS: set[str] = {".pdf", ".jpg", ".jpeg", ".png"}
    ALLOWED_MIME_TYPES: set[str] = {
        "application/pdf",
        "image/jpeg",
        "image/png",
    }

    # --- AI / OCR ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    # If a PDF yields at least this many characters of embedded text, we skip
    # the vision model and parse the text directly. Saves cost and latency.
    NATIVE_TEXT_THRESHOLD: int = 200

    # --- CORS ---
    # Comma-separated list in the env file, e.g. "http://localhost:5173,https://app.vercel.app"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached so the .env file is only read once per process."""
    return Settings()


settings = get_settings()

# Make sure the storage directories exist before anything tries to write to them.
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.REPORT_DIR.mkdir(parents=True, exist_ok=True)