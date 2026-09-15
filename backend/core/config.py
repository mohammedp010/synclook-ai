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

    # --- Catalog retrieval (RAG) ---
    # Retrieval-trained text encoder; CLIP's text tower is not a search index
    # (77-token cap, caption-aligned). 384-dim must match the pgvector column.
    text_embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    text_embedding_dim: int = 384
    # Cross-encoder that re-scores the fused candidate list. Disabling it falls
    # back to fusion order, which is a meaningful ablation for the eval.
    reranker_enabled: bool = True
    reranker_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # Candidates pulled from each retrieval arm before fusion.
    catalog_retrieval_limit: int = 40
    # Candidates handed to the cross-encoder after fusion.
    catalog_rerank_limit: int = 20
    # Reciprocal-rank-fusion damping. 60 is the value from the original RRF
    # paper and the de-facto default; low enough that top ranks dominate.
    catalog_rrf_k: int = 60
    # Serve shopping results from the local catalog before calling the provider.
    catalog_retrieval_enabled: bool = True
    # Cross-encoder probability a catalog hit must clear to be shown. Measured
    # on outfit-slot queries: an exact match scores >0.99, the right garment in
    # the wrong colour ~0.58, the wrong style <0.01 — so 0.5 keeps near-misses
    # when nothing better exists and drops the rest.
    catalog_min_score: float = 0.5
    # Availability freshness. A catalog row asserts a product was buyable when
    # it was last confirmed; past this many days that assertion is no longer
    # credible, so retrieval stops making it and the slot falls through to live
    # search. 0 disables the window. Keeping rows inside it is the refresh
    # job's job: `catalog_ingest --refresh`.
    catalog_stale_after_days: int = 30

    # --- Langfuse (LLM/agent observability) ---
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- SerpAPI (Product Search) ---
    serpapi_api_key: str = ""
    shopping_enabled: bool = True
    # "embedding" ranks products by CLIP similarity to the desired-item spec;
    # "keyword" is the legacy title-token matcher (kept for eval comparison).
    shopping_matcher: str = "embedding"
    shopping_match_threshold: float = 0.75
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
