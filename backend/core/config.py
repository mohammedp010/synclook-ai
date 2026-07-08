"""Application configuration management via environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "Synclook"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    # --- API ---
    api_prefix: str = "/api/v1"
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8081",
        "http://localhost:8082",
        "http://localhost:19006",
        "http://127.0.0.1:8081",
        "http://127.0.0.1:8082",
    ]

    # --- Upload ---
    upload_dir: Path = Path("uploads")
    max_upload_size_mb: int = 10
    allowed_image_types: list[str] = ["image/jpeg", "image/png", "image/webp"]

    # --- Database (PostgreSQL) ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/synclook"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"
    redis_ttl_seconds: int = 3600

    # --- DeepSeek LLM ---
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024

    # --- Vision Models ---
    clip_model_name: str = "openai/clip-vit-base-patch32"
    blip_model_name: str = "Salesforce/blip-image-captioning-base"
    vision_device: str = "cpu"  # "cpu", "cuda", or "mps"
    vision_low_confidence_threshold: float = 0.5
    vision_use_center_crop: bool = False
    vision_center_crop_ratio: float = 0.85
    vision_enable_caption: bool = False  # BLIP is ~1GB; caption is display-only metadata

    # --- SerpAPI (Product Search) ---
    serpapi_api_key: str = ""
    shopping_enabled: bool = True
    shopping_cache_ttl_seconds: int = 604800  # 7 days
    shopping_results_per_item: int = 2
    shopping_country: str = "in"  # gl parameter for SerpAPI

    # --- Rate Limiting ---
    rate_limit: str = "60/minute"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
