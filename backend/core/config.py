"""Application configuration management via environment variables."""

import re
from functools import lru_cache

from pydantic import Field, field_validator
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
    # Browser origins allowed to call the API (a JSON list in the env). Swagger at /docs is same-origin and
    # MCP hosts call server to server, so the deployed demo needs none until a frontend exists.
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8081",
        "http://localhost:8082",
        "http://localhost:19006",
        "http://127.0.0.1:8081",
        "http://127.0.0.1:8082",
    ]

    # --- Upload ---
    max_upload_size_mb: int = 10  # phone photos are 2-8 MB; stored resized to 512 px
    allowed_image_types: list[str] = ["image/jpeg", "image/png", "image/webp"]

    # --- Database (PostgreSQL) ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/synclook"

    # --- Text model (OpenRouter, the same key and base URL as vlm_*) ---
    text_model: str = "google/gemini-2.5-flash-lite"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024
    # The chat agent's model (tool calling), measured by evaluation/agent_tools.py on 21 requests:
    # gpt-4o-mini 21/21 right tool and arguments, 0 empty steps, ~$0.81 per 1,000 turns;
    # gemini-2.5-flash-lite 19/21 and 6 empty replies after a tool result (~$0.50); gpt-4.1-nano 18/21.
    agent_model: str = "openai/gpt-4o-mini"

    # Jev (TypeSafe System One) — typed, calibrated classification.
    jev_api_key: str = ""
    jev_base_url: str = "https://api.typesafe.ai"
    # Pinned, not an alias. Aliases move when releases ship, and confidence
    # thresholds are version-specific — a silent model bump would silently
    # recalibrate every gate. The response's own `model` field is logged so a
    # mismatch is visible rather than inferred.
    jev_model: str = "jev-1.13.0"
    # Measured at ~400ms per call (the docs say ~100ms); 3s means something is wrong.
    jev_timeout_seconds: float = 3.0
    # Retries on 429/529/5xx only; never on 422 (our bug) and never on timeout.
    jev_max_retries: int = 2

    # Budget multimodal model — describes the garment; never classifies it.
    # OpenAI-compatible, so any gateway works with a base-URL change.
    vlm_api_key: str = ""
    vlm_base_url: str = "https://openrouter.ai/api/v1"
    # Chosen from a 4-model benchmark on the public split (evaluation/perception.py --vlm):
    # best on type, formality and aesthetic, ~$0.21 per 1000 analyses, p95 3.3 s.
    vlm_model: str = "google/gemini-2.5-flash-lite"
    # p95 was 3.3 s.
    vlm_timeout_seconds: float = 8.0
    vlm_max_tokens: int = 600
    # Perceptual-hash cache. Demo traffic re-uploads the same few photos
    # constantly, and the VLM is the only line item in the request that costs
    # real money, so this carries most of a demo on its own.
    perception_cache_ttl_seconds: int = 604800  # 7 days

    # --- Langfuse (LLM/agent observability) ---
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- SerpAPI (Product Search) ---
    serpapi_api_key: str = ""
    shopping_enabled: bool = True
    # Products are always checked by Jev (services/product_judge.gate): held-out
    # F1 0.946 vs keyword 0.638. When Jev fails no products are shown.
    shopping_cache_ttl_seconds: int = 604800  # 7 days
    # One provider query returns ~40 products at the same price, so keep a pool
    # for the product gate: with only 2 candidates, two colourless titles
    # ("Men Slim Fit Jeans") emptied the slot. Live, 8 still left "white shoes"
    # empty (no title named a colour); the gate is one batched call either way.
    shopping_candidates_per_query: int = 16
    shopping_country: str = "in"  # gl parameter for SerpAPI
    # --- Daily caps on paid calls, all visitors together (core/budget.py; counted in Postgres) ---
    # Product searches (route, chat and MCP): the free SerpAPI plan is 250 a month (~8 a day), and every
    # search also costs one Jev call.
    search_daily_cap: int = 8
    # Photo uploads: 1 VLM call (~$0.0002) + 1 Jev call each.
    upload_daily_cap: int = 20
    # Chat turns: measured 4.8k tokens on gpt-4o-mini (~$0.0008); at most 6 steps / 20k tokens (~$0.005).
    # So 50 turns are ~$0.04 a day typical and $0.25 at worst.
    chat_daily_cap: int = 50
    # Model-written outfit explanations and free-text occasions on POST /outfits (~$0.0002 each on Gemini
    # Flash-Lite). Over the cap, outfits still come back with rule-based explanations.
    explanation_daily_cap: int = 200

    # --- Rate limiting, per visitor IP (core/rate_limit.py; in memory, so it resets on a restart) ---
    rate_limit: str = "60/minute"  # every route and the MCP endpoint
    paid_rate_limit: str = "20/hour"  # photo uploads and chat turns
    search_rate_limit: str = "3/hour"  # product searches: one visitor cannot spend the whole day's 8

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, url: str) -> str:
        """Hosts (Neon, Render) hand out libpq URLs: ``postgresql://…?sslmode=require&channel_binding=require``.

        asyncpg needs its own scheme, spells the TLS option ``ssl`` and has no channel binding option.
        """
        url = re.sub(r"^postgres(ql)?://", "postgresql+asyncpg://", url)
        url = re.sub(r"[?&]channel_binding=[^&]*", "", url).replace("sslmode=", "ssl=")
        return url if "?" in url or "&" not in url else url.replace("&", "?", 1)

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
