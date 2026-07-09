# Synclook AI — Progress Tracker

> **IMPORTANT**: Update this file after every implementation step so a new chat session can pick up exactly where we left off.

---

## Project Overview

**Synclook AI** is a production-oriented **multi-agent AI fashion recommendation pipeline**. Users upload a clothing image, the system detects clothing attributes (type, color, pattern, style) using computer vision, then a sequence of specialized agents generates outfit recommendations using deterministic styling rules. DeepSeek LLM is optional and is used only to refine the wording of rule-generated explanations; it does not choose outfit items or override styling constraints.

### Core Architecture

```
User uploads image (+ optional free-text intent)
    ↓
LangGraph StateGraph (planner-routed, Phase 2):
  [IntentAgent]    → DeepSeek structured output → validated StyleIntent (heuristic fallback)
  [VisionAgent]    → CLIP zero-shot (1 image pass, cached text embeddings) + optional BLIP
  [StylingAgent]   → Rule engine constrained by effective style + avoid list
  [RecommendationAgent] → structure-driven looks + rule evidence + LLM-grounded explanations
  [ShoppingAgent]  → SerpAPI products (conditional edge: skipped when intent declines)
  [VerifierAgent]  → deterministic quality gate + LLM critic; fixable issues → 1 rebuild cycle
    ↓
[Orchestrator façade]  →  same run()/run_stream() API over the compiled graph
    ↓
[Memory]  →  Redis preferences & history   [Tracing]  →  Langfuse spans + token usage
    ↓
[Streaming]  →  SSE streams per-node progress to frontend
```

### Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Package manager | **Poetry 2.3.3** | Lockfile, dependency groups |
| Python version | **3.12** (Homebrew) | Latest stable, required by deps |
| Web framework | **FastAPI** | Async, Pydantic v2, OpenAPI docs |
| Vision models | **CLIP** (`openai/clip-vit-base-patch32`) + **BLIP** (`Salesforce/blip-image-captioning-base`) | Local inference, no API costs |
| LLM | **DeepSeek** (OpenAI-compatible API) | Intent extraction (structured output), evidence-grounded explanations, verifier critique — outfit selection stays rule-based |
| Styling engine | **Rule-based** (deterministic) | Predictable, fast; acts as guardrails around LLM-proposed intent |
| Orchestration | **LangGraph StateGraph** | Conditional routing + verifier retry cycle; hand-rolled loop couldn't express cycles |
| Observability | **Langfuse** (optional) | Agent spans, LLM generations, token usage; no-op without keys |
| Database | **PostgreSQL** via asyncpg + SQLAlchemy async | Production-grade, JSONB support |
| Cache/Memory | **Redis** | Fast KV store, TTL, pub/sub for streaming |
| Product Search | **SerpAPI** (Google Shopping) | Real product links from Amazon.in, Myntra, etc. Cached in Redis (7d TTL) |
| Logging | **structlog** | Structured JSON logging |
| Rate limiting | **slowapi** | Per-endpoint rate limiting |

---

## Environment Setup

```bash
# Python 3.12 (Homebrew)
/opt/homebrew/bin/python3.12

# Poetry — MUST export PATH before every command
export PATH="/Users/mohd/.local/bin:$PATH"

# Virtualenv
# Name: synclook-ai-TSXNgCCZ-py3.12
# Location: /Users/mohd/Library/Caches/pypoetry/virtualenvs/

# Run commands
cd /Users/mohd/styleforgeai
export PATH="/Users/mohd/.local/bin:$PATH" && poetry run python <script.py>
export PATH="/Users/mohd/.local/bin:$PATH" && poetry run uvicorn main:app --reload

# Vision models cached in HuggingFace cache (~1.6GB total)
# CLIP: ~605MB, BLIP: ~990MB — already downloaded
```

---

## Project Structure

```
styleforgeai/
├── main.py                          # ASGI entrypoint: create_app()
├── pyproject.toml                   # Poetry config, all dependencies
├── poetry.lock
├── .env / .env.example
├── .gitignore
├── uploads/.gitkeep
│
├── backend/
│   ├── __init__.py
│   ├── app.py                       # FastAPI factory: create_app() with CORS, rate limiting, routes
│   │
│   ├── core/
│   │   ├── config.py                # pydantic-settings: Settings class (DB, Redis, LLM, vision, etc.)
│   │   ├── dependencies.py          # DI: get_vision_service(), get_vision_agent(), get_styling_agent(), get_recommendation_agent()
│   │   ├── exceptions.py            # SynclookError, ImageProcessingError, AgentError, LLMError, ToolError
│   │   ├── lifespan.py              # Startup/shutdown lifecycle
│   │   ├── logging.py               # structlog setup_logging() + get_logger()
│   │   └── rate_limit.py            # slowapi limiter
│   │
│   ├── schemas/
│   │   ├── clothing.py              # Enums: ClothingType(18), Color(18), Pattern(8), Style(8) + ClothingAttributes model
│   │   └── api.py                   # AnalysisRequest/Response, Recommendation, RecommendationItem, FeedbackRequest/Response, HealthResponse
│   │
│   ├── services/
│   │   ├── vision.py                # VisionService: CLIP zero-shot + BLIP captioning, async via ThreadPoolExecutor
│   │   ├── llm.py                   # LLMService: DeepSeek async wrapper, tone refinement for rule-generated text
│   │   ├── memory.py                # MemoryService: Redis-backed preferences + analysis history
│   │   ├── product_search.py        # ProductSearchService: SerpAPI async wrapper, query builder, result parser
│   │   └── feedback.py              # FeedbackService: DB persistence + memory updates for feedback + analysis
│   │
│   ├── agents/
│   │   ├── __init__.py              # Re-exports: AgentContext, BaseAgent, VisionAgent, StylingAgent, RecommendationAgent, Orchestrator
│   │   ├── base.py                  # BaseAgent ABC (state tracking, timing, error handling) + AgentContext dataclass + StyleMatch
│   │   ├── orchestrator.py          # Orchestrator: chains Vision→Styling→Recommendation, error recovery
│   │   ├── vision_agent.py          # VisionAgent: wraps VisionService → populates ctx.clothing_attributes
│   │   ├── styling_agent.py         # StylingAgent: rule-based COLOR_COMPLEMENTS, ITEM_PAIRINGS, STYLE_COMPATIBILITY, PATTERN_PAIRS
│   │   ├── recommendation_agent.py  # RecommendationAgent: builds 3 diversified Recommendation objects from StyleMatches
│   │   └── shopping_agent.py        # ShoppingAgent: attaches real ProductLinks from SerpAPI to each RecommendationItem
│   │
│   ├── api/routes/
│   │   ├── health.py                # GET /api/v1/health
│   │   ├── analysis.py              # POST /api/v1/analyze (image upload → VisionService → response)
│   │   ├── feedback.py              # POST /api/v1/feedback (skeleton — persistence in Step 8)
│   │   └── stream.py                # SSE streaming — POST /api/v1/analyze/stream (Step 9)
│   │
│   ├── db/
│   │   ├── base.py                  # SQLAlchemy DeclarativeBase
│   │   ├── session.py               # Async engine + session factory
│   │   └── redis.py                 # Redis async client: get_redis(), close_redis()
│   │
│   ├── models/
│   │   └── records.py               # ORM: AnalysisRecord, FeedbackRecord (UUID PKs, JSONB)
│   │
│   └── tools/
│       ├── __init__.py              # Re-exports: ColorMatcherTool, StyleRuleEngineTool, ProductSearchTool
│       ├── color_matcher.py         # ColorMatcherTool: complement lookups, pair scoring
│       ├── style_rules.py           # StyleRuleEngineTool: item pairings, style/pattern compat, scoring
│       └── product_search.py        # ProductSearchTool: Redis cache-first product lookup
│
├── tests/
│   ├── conftest.py                  # Shared fixtures (sample_attributes, mock_vision_service, etc.)
│   ├── unit/
│   │   ├── agents/
│   │   │   ├── test_vision_agent.py     # 7 tests
│   │   │   ├── test_styling_agent.py    # 9 tests
│   │   │   └── test_recommendation_agent.py # 12 tests
│   │   ├── tools/
│   │   │   ├── test_color_matcher.py    # 14 tests
│   │   │   └── test_style_rules.py      # 14 tests
│   │   ├── test_llm_service.py          # 5 tests
│   │   └── test_schemas.py              # 12 tests
│   └── integration/
│       ├── test_orchestrator.py         # 15 tests
│       └── test_api.py                  # 8 tests (httpx AsyncClient + mocked deps)
│   └── integration/__init__.py
│
├── smoke_test.py                    # API endpoint smoke test (Step 1)
├── test_vision.py                   # Vision pipeline test (Step 2)
└── test_agents.py                   # Multi-agent pipeline test (Step 3)
```

---

## Dependencies (pyproject.toml)

**Runtime**: fastapi, uvicorn[standard], pydantic, pydantic-settings, python-multipart, pillow, openai, httpx, structlog, redis, asyncpg, sqlalchemy[asyncio], alembic, python-dotenv, sse-starlette, slowapi, torch, torchvision, transformers

**Dev**: pytest, pytest-asyncio, pytest-cov, httpx, ruff, mypy

---

## Implementation Steps — Status

### ✅ Step 1: Project Setup + FastAPI Skeleton
- Poetry project initialized with Python 3.12
- Full directory structure created
- FastAPI app factory (`create_app()`) with CORS, rate limiting
- 4 route groups: health, analysis, feedback, stream
- Config via pydantic-settings (`.env` support)
- Structured logging via structlog
- Custom exception hierarchy
- ORM models for AnalysisRecord and FeedbackRecord
- Async DB session factory + Redis client
- **Verified**: smoke test passes all 4 endpoints

### ✅ Step 2: Vision Service (CLIP + BLIP)
- `VisionService` with lazy-loaded CLIP + BLIP models
- CLIP zero-shot classification with per-attribute prompt maps (clothing type, color, pattern, style)
- BLIP image captioning (max 64 tokens)
- Inference offloaded to `ThreadPoolExecutor(max_workers=2)`
- Models cached via `_ModelHolder` singleton + `@lru_cache`
- Analysis route updated to use real VisionService via DI
- **Verified**: test_vision.py — shirt/navy/polka_dot/minimalist, conf=0.505

### ✅ Step 3: Multi-Agent Pipeline
- `BaseAgent` ABC with `run()` → `_execute()` pattern, state tracking, timing, error handling
- `AgentContext` dataclass: flows through pipeline carrying image_bytes → clothing_attributes → style_matches → recommendations
- `StyleMatch` dataclass for intermediate styling results
- `VisionAgent`: wraps VisionService, populates `ctx.clothing_attributes`
- `StylingAgent`: rule-based engine with 4 rule tables:
  - `COLOR_COMPLEMENTS` — 18 colors, each with 3-6 complementary colors
  - `ITEM_PAIRINGS` — 16 clothing types mapped to suggested pairings
  - `STYLE_COMPATIBILITY` — 8 styles with compatible style lists
  - `PATTERN_PAIRS` — 8 patterns with pairing rules (solid pairs with everything)
- `RecommendationAgent`: converts StyleMatches → up to 3 Recommendation objects with color diversity, template explanations
- Dependencies updated with `get_vision_agent()`, `get_styling_agent()`, `get_recommendation_agent()`
- **Verified**: test_agents.py — full pipeline VisionAgent(15s) → StylingAgent(0.001s) → RecommendationAgent(0.005s)

### ✅ Step 4: Implement Tools
- `ColorMatcherTool` (`backend/tools/color_matcher.py`): color complement lookups, compatibility checks, pair scoring, best-color selection
- `StyleRuleEngineTool` (`backend/tools/style_rules.py`): item pairing lookups, style/pattern compatibility checks, composite match scoring
- Tools are callable utility classes that agents invoke — separate from agent logic
- Rule tables (COLOR_COMPLEMENTS, ITEM_PAIRINGS, STYLE_COMPATIBILITY, PATTERN_PAIRS) moved from StylingAgent into tools
- StylingAgent refactored to instantiate and delegate to both tools
- Backward-compatible re-exports kept in `styling_agent.py` for any external imports
- **Verified**: test_agents.py — full pipeline passes, identical output to Step 3

### ✅ Step 5: Implement Orchestrator
- `Orchestrator` class in `backend/agents/orchestrator.py`
- Chains agents: VisionAgent → StylingAgent → RecommendationAgent in sequence
- Manages `AgentContext` lifecycle: creates context, passes through pipeline, returns final state
- Error recovery: VisionAgent failure is fatal (re-raised), downstream failures are non-fatal (partial results returned, error logged in `ctx.errors`)
- Total pipeline timing tracked in `ctx.metadata["total_elapsed_s"]`
- Added `get_orchestrator()` to DI container (`backend/core/dependencies.py`)
- `/api/v1/analyze` route rewritten to use `Orchestrator` — now returns full recommendations instead of empty list
- Orchestrator exported from `backend/agents/__init__.py`
- **Verified**: Orchestrator test — 3 recommendations, 4 style matches, total=15.3s, no errors

### ✅ Step 6: Integrate LLM (DeepSeek)
- `LLMService` in `backend/services/llm.py`: async wrapper around DeepSeek API (OpenAI-compatible)
- Two generation methods: `generate_outfit_explanation()` and `generate_item_reason()`
- System prompt constrains output to short, friendly fashion-stylist advice (<100 words, no markdown)
- **Only tone-refines**: `overall_explanation` in Recommendation and `reason` in RecommendationItem
- Graceful fallback: if `DEEPSEEK_API_KEY` is empty, LLM is disabled and template strings are used
- Graceful fallback: if API call fails (connection/rate-limit/error), `LLMError` is caught and templates are preserved
- `RecommendationAgent` updated: accepts optional `LLMService`, calls `_enrich_recommendation()` per outfit
- `Orchestrator` updated: accepts optional `LLMService`, passes it to `RecommendationAgent`
- DI updated: `get_llm_service()` singleton, wired into `get_recommendation_agent()` and `get_orchestrator()`
- **Verified**: pipeline passes with `llm_enabled=False` (no API key) — template fallback works, 3 recommendations, no errors
- To activate: set `DEEPSEEK_API_KEY` in `.env`

### ✅ Step 7: Add Memory (Redis)
- Redis installed via Homebrew (`brew install redis`), running as background service
- `MemoryService` in `backend/services/memory.py`: Redis-backed user preferences + analysis history
- `UserPreferences` class: tracks liked/disliked colors and styles per user
- `record_feedback()`: updates preferences based on like/dislike feedback
- `save_analysis()`: appends detected attributes to user history (capped at 10 entries, LIFO)
- `get_preferences()` / `get_history()`: load user data with TTL-based expiry
- Orchestrator wired: loads preferences before pipeline, saves analysis after pipeline
- StylingAgent enhanced: boosts scores (+0.05) for liked colors/styles, penalises (-0.1) for disliked ones
- Preferences injected into `ctx.metadata["user_preferences"]` for downstream agent access
- `get_memory_service()` added to DI container, lifespan updated to close on shutdown
- **Verified**: test_memory.py — preferences stored/loaded, history grows, score adjustments applied, no errors

### ✅ Step 8: Add Feedback Loop
- `FeedbackService` in `backend/services/feedback.py`: bridges DB persistence and Redis memory updates
- `save_analysis()`: persists AnalysisRecord to PostgreSQL (request_id, user_id, detected_attributes JSONB, recommendations JSONB)
- `record_feedback()`: persists FeedbackRecord to PostgreSQL, then extracts colors/styles from the matching AnalysisRecord and calls `MemoryService.record_feedback()` to update user preferences in Redis
- Feedback route (`POST /api/v1/feedback`) wired to FeedbackService + DB session
- Analysis route (`POST /api/v1/analyze`) now persists analysis to PostgreSQL after pipeline completes (non-blocking — failure is logged but doesn't break the response)
- PostgreSQL setup: `synclook` database created, tables (`analysis_records`, `feedback_records`) auto-created via SQLAlchemy `create_all`
- `.env` updated: `DATABASE_URL=postgresql+asyncpg://mohd@localhost:5432/synclook`
- `greenlet` added as dependency (required by SQLAlchemy async)
- `get_feedback_service()` added to DI container
- **Verified**: test_feedback.py — analysis persisted, feedback persisted (like + dislike), memory updated with colors/styles, DB totals correct

### ✅ Step 9: Add Streaming (SSE)
- Added `run_stream()` async generator to `Orchestrator` — yields SSE event dicts (`status`, `agent_done`, `warning`, `error`, `result`, `done`)
- Implemented `POST /api/v1/analyze/stream` in `backend/api/routes/stream.py` using `sse_starlette.EventSourceResponse`
- Registered stream route in `backend/app.py`
- Verified: all events stream correctly — status per agent, final `result` with full `AnalysisResponse` JSON, `done` with elapsed time
- Error handling: vision failures emit `error` event and stop; downstream failures emit `warning` and return partial results

### ✅ Step 10: Add Tests
- **104 tests, all passing in ~0.45s** (no real models/API/DB needed)
- `tests/conftest.py` — shared fixtures: `sample_attributes`, `sample_context`, `sample_context_with_matches`, `mock_vision_service`
- `tests/unit/tools/test_color_matcher.py` — 14 tests: complements, compatibility, scoring, all-color coverage
- `tests/unit/tools/test_style_rules.py` — 14 tests: item pairings, style/pattern compatibility, composite scoring
- `tests/unit/agents/test_vision_agent.py` — 7 tests: attribute population, error handling, state transitions, timing
- `tests/unit/agents/test_styling_agent.py` — 9 tests: match generation, preference boost/penalty, all clothing types
- `tests/unit/agents/test_recommendation_agent.py` — 12 tests: build/diversify helpers, LLM tone refinement + fallback, error paths
- `tests/unit/test_llm_service.py` — 5 tests: disabled/enabled states, error on disabled
- `tests/unit/test_schemas.py` — 12 tests: schema construction, validation, serialization roundtrips
- `tests/integration/test_orchestrator.py` — 15 tests: full pipeline, streaming, partial results, memory integration
- `tests/integration/test_api.py` — 8 tests: health, analyze, stream endpoints via httpx AsyncClient with mocked deps
- Run: `poetry run python -m pytest tests/ -v`

### ✅ Step 11: Deployment Config
- **Dockerfile**: Multi-stage build (builder + runtime), `python:3.12-slim`, non-root `synclook` user, healthcheck via curl, CMD: uvicorn with 2 workers
- **docker-compose.yml**: 3 services (app, PostgreSQL 16-alpine, Redis 7-alpine), health checks on all, named volumes (`pgdata`, `redisdata`, `uploads`), depends_on healthy
- **.env.docker**: Production environment config (`DATABASE_URL=postgresql+asyncpg://synclook:synclook_secret@postgres:5432/synclook`, `REDIS_URL=redis://redis:6379/0`)
- **.dockerignore**: Excludes `__pycache__`, `.env` (except `.env.docker`), venv, node_modules
- **Alembic**: Async migration runner (`alembic/env.py` uses app `Settings` + `Base` metadata), initial migration `02b9134af48d` (empty since tables pre-existed), DB stamped at head
- Health check endpoints already existed from Step 1 (`GET /api/v1/health`)
- **Verified**: 104 tests still passing after all deployment changes

### ✅ Step 12: Shopping Agent (Product Search)
- `ProductSearchService` in `backend/services/product_search.py`: async SerpAPI wrapper via httpx, query builder, result parser
- `ProductSearchTool` in `backend/tools/product_search.py`: Redis cache-first lookup, calls SerpAPI on miss, stores results with 7-day TTL
- `ShoppingAgent` in `backend/agents/shopping_agent.py`: BaseAgent that iterates RecommendationItems, deduplicates queries by (item_type, color, style), attaches `ProductLink` objects
- `ProductLink` schema: `title`, `price`, `link` (buy URL), `thumbnail` (product image), `source` (store name)
- `Gender` enum added to schemas: `male`, `female`, `unisex` — controls search query specificity
- `AgentContext` extended: `gender` (default="unisex") and `include_products` (default=True) fields
- `Orchestrator` updated: 4-agent pipeline (Vision → Styling → Recommendation → Shopping), accepts `product_tool`
- API routes updated: `POST /api/v1/analyze` and `POST /api/v1/analyze/stream` accept `gender` and `include_products` params
- DI updated: `get_product_search_service()`, `get_product_search_tool()` (async — needs Redis), wired into `get_orchestrator()`
- Config: `SERPAPI_API_KEY`, `SHOPPING_CACHE_TTL_SECONDS` (604800 = 7d), `SHOPPING_RESULTS_PER_ITEM` (2), `SHOPPING_COUNTRY` ("in")
- Graceful fallback: if `SERPAPI_API_KEY` is empty, ShoppingAgent is skipped (same pattern as DeepSeek)
- Cost optimization: query deduplication (same item+color+style across recommendations = 1 API call), Redis caching (7-day TTL)
- **Verified**: 125 tests passing (21 new: 10 ProductSearchService, 4 ProductSearchTool, 7 ShoppingAgent)

---

## Quality Optimization Sprint (Post-Launch)

### ✅ Step 13: Domain Constraints + Taxonomy (Requested Step 1)
- Added deterministic gender constraints in style engine: `INVALID_ITEMS_BY_GENDER`
- Added clothing taxonomy map: `CLOTHING_TYPE_CATEGORIES` with categories (`topwear`, `bottomwear`, `outerwear`); later expanded in Step 27 with active `footwear` and `accessory` categories
- `StyleRuleEngineTool.get_paired_items()` now supports optional `gender` filter (backward compatible default: `unisex`)
- `StylingAgent` now filters candidate item types by user gender
- `RecommendationAgent` now filters style matches by gender before building looks
- `ShoppingAgent` now post-filters products that violate gender constraints and skips invalid recommendation items
- Added regression tests to prevent male/blouse mismatch recurrence:
    - `tests/unit/tools/test_style_rules.py` (taxonomy + gender filter)
    - `tests/unit/agents/test_styling_agent.py` (male trousers excludes blouse)
    - `tests/unit/agents/test_recommendation_agent.py` (gender filter in output)
    - `tests/unit/agents/test_shopping_agent.py` (post-filter product titles)
- **Verified**: `69 passed` across targeted rule/agent test suite

### ✅ Step 14: Outfit Structure Engine (Requested Step 2)
- Added deterministic `OUTFIT_STRUCTURE` contract in style rules:
    - `bottomwear` → required: `topwear`, optional: `outerwear`
    - `topwear` → required: `bottomwear`, optional: none
- Added `StyleRuleEngineTool.get_outfit_structure()` helper for reusable policy access
- Reworked `RecommendationAgent` item assembly to be structure-driven:
    - Enforces required categories first
    - Adds at most one optional category item
    - Prevents duplicate item types in a look
    - Capped recommendation items to structured limit (`MAX_ITEMS_PER_OUTFIT=2` at this step; raised to 4 in Step 27)
- Added tests for structured output constraints:
    - `tests/unit/agents/test_recommendation_agent.py::test_bottomwear_look_has_single_topwear`
    - `tests/unit/agents/test_recommendation_agent.py::test_streetwear_bottomwear_skips_outerwear`
- **Verified**: `38 passed` for style-rule + recommendation test subset
### ✅ Step 15: Style-Constraint Filtering (Requested Step 3)
- Added deterministic style policy table `STYLE_ALLOWED_ITEMS` in rule engine
- Added `StyleRuleEngineTool.is_item_allowed_for_style()`
- Enforced style-policy filtering in:
    - `StylingAgent` (candidate match generation)
    - `RecommendationAgent` (second-pass safety filtering)
- Key rule impact now in code:
    - `streetwear` excludes formal-heavy items like `blazer`
    - `formal` allows `shirt` + `blazer` combinations
    - `casual` remains flexible but constrained to casual-safe items
- Added regression tests:
    - `tests/unit/tools/test_style_rules.py` (streetwear disallow / formal allow)
    - `tests/unit/agents/test_styling_agent.py` (streetwear trousers excludes blazer)
- **Verified**: `51 passed` for style-rule + styling + recommendation subset
### ✅ Step 16: Vision Noise Reduction (Requested Step 4)
- Added configurable confidence gating:
    - `vision_low_confidence_threshold` (default: `0.5`)
    - On low confidence, `StylingAgent` switches to conservative fallback item policy
    - Flag exposed in context metadata: `low_confidence_detection`
- Added optional lightweight preprocessing:
    - `vision_use_center_crop` (default: `False`)
    - `vision_center_crop_ratio` (default: `0.85`)
    - Center-crop helper reduces scene/background noise without heavy models
- Clarified BLIP caption handling:
    - Caption remains display metadata only
    - Not used in decision logic
- Added safe fallback API in style engine:
    - `StyleRuleEngineTool.get_safe_fallback_items()`
- Added regression tests for low-confidence safety path
- **Verified**: `35 passed` for style-rule + styling subset after gating changes
### ✅ Step 17: Fashion Knowledge Base + Service (Requested Step 5)
- Added JSON knowledge base: `backend/data/fashion_knowledge.json`
    - Encodes category, best matches, avoid lists, and style-specific pairings
    - Includes deterministic constraints for key garments (trousers, jeans, chinos, shirt, t-shirt, hoodie, etc.)
- Added `FashionKnowledgeService` (`backend/services/fashion_knowledge.py`)
    - Loads and validates JSON knowledge
    - APIs: `get_best_matches()`, `get_avoid_items()`, `is_forbidden_pair()`, `to_clothing_types()`, `get_category()`
- Integrated knowledge service into pipeline:
    - `StylingAgent` uses knowledge-ranked matches and avoid constraints
    - `RecommendationAgent` uses knowledge for match filtering and deterministic ranking
    - `Orchestrator` injects a shared `FashionKnowledgeService` instance into both agents
    - DI container updated with `get_fashion_knowledge_service()`
- Added unit tests: `tests/unit/test_fashion_knowledge_service.py`
- **Verified**: `49 passed` across knowledge + agent + orchestrator subset
### ✅ Step 18: Shopping Relevance Improvements (Requested Step 6)
- `ProductSearchService.build_query()` now builds structured, gender-aware queries:
    - format: `men|women|unisex {color} {item} {style}`
    - adds deterministic negative tokens (e.g. `-blouse -women -dress`) for male search intent
- `ShoppingAgent` post-filtering upgraded:
    - keeps gender-invalid products out of results
    - validates product titles against allowed item-type keywords/synonyms (e.g. shirt, blazer, t-shirt)
    - drops mismatched product titles from recommendation items
- Existing deduplication and cache behavior preserved
- Added/updated shopping tests for:
    - structured query output
    - negative keyword inclusion
    - gender + item-type product filtering
- **Verified**: `24 passed` in `tests/unit/agents/test_shopping_agent.py`
### ✅ Step 19: Recommendation Logic Rewrite (Requested Step 7)
- Finalized deterministic look assembly contract in `RecommendationAgent`:
    - For bottomwear inputs: exactly 1 topwear is required
    - Optional outerwear limited to max 1
    - Max extras per look remains hard-capped at 2
    - Duplicate item types prevented within a look
- Added payload cleanup:
    - `style_tags` now deduplicated (`streetwear` no longer repeated 3-4 times)
- Existing LLM integration preserved (text-only tone refinement after deterministic item selection)
- Added tests for:
    - style tag deduplication
    - maximum items per structured look
    - bottomwear outfit contract behavior
- **Verified**: `20 passed` in recommendation unit tests
### ✅ Step 20: Explanation Control (Requested Step 8)
- Explanation pipeline is now rule-first and deterministic:
    - `RecommendationAgent` always builds factual template reasons/explanations from rule outputs
- LLM usage narrowed to **tone refinement only**:
    - `LLMService` prompts now explicitly forbid adding/removing items, colors, styles, or constraints
    - LLM receives deterministic `rule_text` and rewrites wording only
- Updated integration points:
    - `generate_outfit_explanation(..., rule_text=...)`
    - `generate_item_reason(..., rule_text=...)`
- Updated tests for new LLM method signatures and recommendation tone-refinement flow
- **Verified**: `25 passed` for LLM + recommendation subset
### ✅ Step 21: Evaluation Harness (Requested Step 9)
- Added deterministic evaluation suite:
    - `evaluation/test_cases.json` with expected + forbidden item contracts
    - `evaluation/harness.py` to execute style/recommendation pipeline over cases
- Metrics implemented:
    - `invalid_item_rate`
    - `gender_mismatch_rate`
    - `recommendation_consistency_error_rate`
- Added test coverage: `tests/unit/test_evaluation_harness.py`
- Initial baseline run:
    - `invalid_item_rate = 0.0`
    - `gender_mismatch_rate = 0.0`
    - `recommendation_consistency_error_rate = 0.25`

### ✅ Step 23: Calibration Pass (Consistency < 0.1)
- Goal: reduce recommendation consistency error from `0.25` to `< 0.1`
- Calibration changes:
    - Expanded trousers pairings to include streetwear-compatible tops (`t-shirt`, `hoodie`) in `ITEM_PAIRINGS`
    - Tightened trousers streetwear ranking in `fashion_knowledge.json` to prioritize `t-shirt`, `hoodie`, `shirt`
    - Added small rank penalty for low-priority alternates in `RecommendationAgent`
    - Added regression guard in `tests/unit/test_evaluation_harness.py`:
      - `recommendation_consistency_error_rate < 0.1`
- Calibrated harness run:
    - `invalid_item_rate = 0.0`
    - `gender_mismatch_rate = 0.0`
    - `recommendation_consistency_error_rate = 0.0`

### ✅ Step 22: UX Improvements (Requested Step 10)
- Backend metadata update:
    - Added `description_relevant` to `ClothingAttributes`
    - Vision service now computes lightweight caption relevance flag via lexical match
- Frontend output cleanup:
    - Results screen now hides noisy caption text when `description_relevant` is false
    - Keeps detected item and confidence visible as primary signals
    - Style-tag duplication already removed from backend (Step 19)
- Updated fixtures/types for schema compatibility

### ✅ Validation Run (Optimization Steps 13–22)
- Executed impacted suite across unit + integration tests
- **Verified**: `112 passed, 3 warnings` (no failures)

### ✅ Validation Run (Post-Calibration)
- Executed impacted unit + integration suite after Step 23
- **Verified**: `108 passed, 3 warnings` (no failures)

### 📱 Frontend Integration Guide
- **Comprehensive React Native guide** written in [`FRONTEND_GUIDE.md`](FRONTEND_GUIDE.md)
- Covers: project setup (Expo SDK 52+), API client layer (Axios), SSE streaming integration, all 4 backend endpoints
- Complete screen implementations: HomeScreen, AnalysisScreen (with real-time SSE progress), ResultsScreen (outfit cards + feedback)
- Custom SVG components: LogoSvg, HangerIcon, SparkleIcon, WardrobeIllustration, AnalyzingWave
- Animation system: React Native Reanimated 3, staggered entries, progress ring, pulsing glows, spring configs
- Design tokens: dark theme (deep purple/slate), Space Grotesk + Inter typography, color mapping
- Responsive layout: `wp()`, `hp()`, `scale()`, `moderateScale()`, device-size breakpoints (small/medium/large/tablet)
- State management: Zustand store (user, analysis, feedback, history)
- Haptic feedback on all interactions (expo-haptics)
- Mock data for offline development
- Baseline API contracts and SSE wiring are integrated; see Step 24 for remaining alignment gaps

### 🟨 Step 24: Frontend Remaining Work (Post-Backend Optimization) — In Progress

The backend optimization/calibration stream (Steps 13-23) is complete and stable. The following frontend tasks are still pending to fully align with current backend behavior and contracts:

#### A) Immediate blockers (fix next)
- [x] **Fix TypeScript build errors**
    - `src/api/__mocks__/mockAnalysis.ts`: add required `description_relevant` and align payload with current response models
    - `src/screens/HomeScreen.tsx`: handle nullable `detected_attributes` in analysis history rendering
- [x] **Fix web CSS side-effect import typing**
    - `index.ts` currently reports: "Cannot find module or type declarations for side-effect import of './global.css'"
    - Add a declaration file (e.g. `global.d.ts`) or switch to the Expo-supported web style path

#### B) Contract alignment with backend routes
- [x] **Split response typings by endpoint**
    - `/api/v1/analyze` should model `AnalysisResponse` from backend (`request_id`, `detected_attributes`, `recommendations`, `created_at`)
    - SSE `result` event should use a dedicated type that includes `errors`
- [x] **Remove stale/ambiguous shared fields**
    - Avoid requiring `errors` on non-stream analysis responses
    - Keep nullable handling only where backend can actually emit null (stream partial/failure contexts)

#### C) UX parity with backend quality improvements
- [x] **Expose partial-result warnings to users**
    - Surface SSE `warning` events in Analysis/Results UI (currently mostly internal)
- [x] **Document/reflect low-confidence mode in UI**
    - Backend now applies conservative fallback logic on low confidence; frontend should show a subtle “safe recommendations mode” indicator when available
- [x] **Add optional include-products toggle**
    - Backend supports `include_products`; frontend currently always sends `true`

#### D) Validation and release hardening
- [ ] **Run and record frontend validation suite**
    - [x] `npx tsc --noEmit`
    - [x] Expo web smoke run (`Web Bundled ... index.ts`)
    - [ ] Device/simulator run (currently blocked by local toolchain setup)
- [ ] **Execute end-to-end regression scenarios for backend fixes**
    - [x] Male trousers scenario parity verified (automated): no blouse/female mismatch
    - [x] Streetwear trousers scenario parity verified (automated): no blazer prioritization regression
    - [x] Irrelevant scene caption suppression path verified in code (`description_relevant` + `showCaption` gate)
    - [ ] Manual device/simulator walkthrough with real uploads still pending

Current Step 24 verification snapshot:
- `npx tsc --noEmit` passed with no TypeScript errors.
- Expo web smoke run succeeded (`Web Bundled ... index.ts`).
- Targeted backend regression checks passed: `13 passed` (`tests/unit/agents/test_styling_agent.py`, `tests/unit/test_evaluation_harness.py`).
- Deterministic harness run passed with all core rates at `0.0`:
    - `invalid_item_rate = 0.0`
    - `gender_mismatch_rate = 0.0`
    - `recommendation_consistency_error_rate = 0.0`
- Full backend regression baseline also passes: `147 passed, 3 warnings` (`python -m pytest -q`).
- iOS simulator run is blocked by local Xcode setup prompt (`expo run:ios` requires full Xcode developer tools installation).
- Android simulator run is blocked by missing Android SDK / `adb` (`expo run:android` failed to resolve SDK path).
- Manual device/simulator walkthrough remains an explicit release gate.

### ✅ Step 25: Stability Bug-Fix Pass (Requested Follow-up)
- Fixed recommendation dead-zone for full-outfit garments:
    - Added item-specific outfit-structure overrides for `dress` and `suit` in style rules
    - Prevents zero-recommendation regressions caused by generic topwear structure requirements
- Fixed frontend API base URL strategy for safer development:
    - Replaced hardcoded localhost-only base URL with environment-first resolution (`EXPO_PUBLIC_API_BASE_URL`)
    - Added platform-safe dev defaults (web hostname-aware, Android emulator `10.0.2.2` fallback)
- Fixed backend HTTP semantics for unexpected analysis failures:
    - `/api/v1/analyze` now returns `500` for internal pipeline errors instead of `400`
    - Added integration regression test for this behavior
- Fixed UTC timestamp deprecation risk:
    - Replaced `datetime.utcnow()` with timezone-aware `datetime.now(timezone.utc)` in API schema defaults and memory history timestamps
- Fixed frontend warning UX state handling:
    - SSE `warning` events no longer mark pipeline stages as `error`; stages remain non-fatal (`done`) while warning text is surfaced
- Fixed SSE parser robustness:
    - `data:` lines are now accumulated per SSE spec (multiline-safe) instead of being overwritten
- Fixed stream resource efficiency on client disconnect:
    - SSE route now checks `request.is_disconnected()` and exits generator early

Step 25 verification snapshot:
- Targeted regressions: `69 passed` (`style_rules`, `recommendation_agent`, `api`, `schemas`, `memory` subsets)
- Full backend suite: `152 passed`
- Frontend type-check: `npx tsc --noEmit` passed
- Frontend web smoke: `CI=1 npx expo start --web --port 8090` bundled successfully (`Web Bundled ... index.ts`)

> Note: The statement "All API contracts, SSE event types, and schema shapes match backend exactly" above is no longer fully accurate until Step 24 tasks are completed.

---

## Next Steps For Current Product Improvement

These are not 2.0 feature expansions. They are targeted fixes for current product flaws that can make the existing Synclook experience more coherent, reliable, and defensible.

### ✅ Step 26: Reposition Agent Claims And Align Documentation
- Fixed current flaw: The tracker described Synclook as a production-grade autonomous agent system, but the current implementation is a deterministic multi-agent pipeline.
- Completed updates:
    - Updated project metadata to "Multi-agent AI fashion recommendation pipeline"
    - Updated Progress overview to clarify deterministic outfit selection and optional LLM tone refinement
    - Updated architecture wording from LLM explanation generation to LLM tone refinement
    - Updated API schema wording so `overall_explanation` is not described as purely LLM-generated
    - Updated LLM/recommendation docstrings to clarify that DeepSeek preserves rule-generated facts
- Verification:
    - `pyproject.toml`, `Progress.md`, API schema descriptions, and LLM/recommendation docstrings no longer imply autonomous outfit selection by the LLM
    - `tests/unit/test_schemas.py` passed after wording changes

### ✅ Step 27: Expand Outfit Completeness
- Fixed current flaw: Recommendation output was capped to very small looks (`MAX_ITEMS_PER_OUTFIT=2`), and footwear/accessories were missing from the active taxonomy.
- Completed updates:
    - Added generic `shoes` and `accessory` clothing types for a conservative v1 taxonomy expansion
    - Added active `footwear` and `accessory` categories in `CLOTHING_TYPE_CATEGORIES`
    - Expanded outfit structures so topwear/bottomwear looks can include required complementary garment plus optional outerwear, footwear, and accessory
    - Raised `MAX_ITEMS_PER_OUTFIT` from 2 to 4 so recommendations can represent more complete looks
    - Added shoes/accessory pairings to deterministic style rules and fashion knowledge rankings
    - Added CLIP prompt coverage and caption relevance aliases for `shoes` and `accessory`
    - Added shopping title synonyms for shoes/accessories so product filtering can keep matching results
    - Updated evaluation fixtures so complete-look items do not count as consistency errors
- Verification:
    - Focused suite passed: `82 passed` (`style_rules`, `styling_agent`, `recommendation_agent`, `fashion_knowledge_service`, `evaluation_harness`, `schemas`)
    - Full backend suite passed: `157 passed`

### ✅ Step 28: Replace Rigid Gender Filtering With Shopping Intent
- Fixed current flaw: Previous `Gender` filtering made product/search constraints feel like identity constraints.
- Completed updates:
    - Added `ShoppingIntent` API enum: `menswear`, `womenswear`, `unisex`, `all`
    - Kept legacy `Gender` query support for backwards-compatible clients
    - Added `AgentContext.shopping_intent` and wired it through orchestrator, styling, recommendation, and shopping agents
    - Normalized legacy values (`male`, `female`, `unisex`) into shopping-intent semantics internally
    - Updated style-rule filtering so `menswear` preserves the previous male/blouse safety behavior while `all` allows broader recommendations
    - Updated fashion-knowledge avoid-list lookup to understand shopping intent
    - Updated product search query building and negative tokens to use shopping intent
    - Updated frontend state/API/SSE calls to send `shopping_intent`
    - Replaced the Home screen "Shopping for" control with a "Shopping intent" control: Menswear, Womenswear, Unisex, All
    - Updated Home screen layout decisions to use wide-viewport breakpoints instead of web-platform checks, preventing narrow web/mobile crowding
- Verification:
    - Focused backend suite passed: `110 passed` (`style_rules`, `styling_agent`, `recommendation_agent`, `shopping_agent`, `fashion_knowledge_service`, `api`)
    - Full backend suite passed: `165 passed`
    - Frontend type-check passed: `npx tsc --noEmit`
    - Expo web smoke bundled successfully on port `8090`
    - Browser layout check passed at `1280x720`: four intent pills visible, no horizontal overflow
    - Browser layout check passed at `390x844`: intent pills wrap into two readable rows, no horizontal overflow

### ✅ Step 29: Improve Shopping Relevance Beyond Title Keywords
- Fixed current flaw: Shopping relevance depended on query strings and simple title keyword filtering with no match evidence.
- Completed updates:
    - Added relevance metadata to `ProductLink`: `match_score` and `match_reason`
    - Kept schema backwards-compatible with defaults so older cached product JSON can still deserialize
    - Replaced binary title-only filtering with a product scoring layer in `ShoppingAgent`
    - Product score now considers item-type keyword match, shopping-intent exclusions, color match, style match, thumbnail presence, price presence, and source presence
    - Products below the minimum match threshold are dropped
    - Kept products are sorted by `match_score` descending
    - Added frontend product type support for optional match metadata
    - Added tests for match metadata and stronger-product reranking
- Verification:
    - Shopping suite passed: `29 passed`
    - Affected suite passed: `51 passed` (`shopping_agent`, `schemas`, `api`)
    - Frontend type-check passed: `npx tsc --noEmit`
    - Full backend suite passed: `167 passed`

### ⬜ Step 30: Strengthen Vision Reliability
- Current flaw: CLIP + BLIP classification is useful but limited for real fashion images with clutter, multiple garments, cropped photos, or ambiguous categories.
- Improve by:
    - Adding garment segmentation or object localization before classification
    - Supporting multi-garment detection instead of assuming one primary item
    - Adding correction UI so users can fix detected type/color/style
    - Saving corrections as supervised feedback for calibration
    - Making low-confidence behavior visible in API metadata, not only inferred from confidence threshold
- Suggested verification:
    - Multiple-garment photos fail gracefully or return selectable detected items
    - User corrections update the recommendation immediately
    - Low-confidence scenarios are represented in evaluation fixtures

### ⬜ Step 31: Expand Evaluation Harness Before Claiming Perfect Quality
- Current flaw: Current calibrated metrics are perfect, but the deterministic evaluation file has only a few cases.
- Improve by:
    - Expanding evaluation fixtures to 100+ cases across garment type, style, color, pattern, confidence, and shopping intent
    - Adding product relevance metrics
    - Adding empty recommendation rate
    - Adding complete outfit rate
    - Adding explanation faithfulness checks
    - Running the harness in CI or as a release gate
- Suggested verification:
    - Harness reports rates over broad fixtures, not only narrow regression examples
    - Each future recommendation change includes before/after metric output

### ⬜ Step 32: Make Explanations Grounded And Traceable
- Current flaw: Explanations are pleasant, but they do not expose enough grounded reasoning to debug or build user trust.
- Improve by:
    - Adding structured rule evidence to each recommendation
    - Adding rejected-candidate reasons for debug/evaluation output
    - Returning concise user-facing reasoning plus optional developer trace
    - Ensuring LLM tone refinement cannot add unsupported claims
- Suggested verification:
    - Every recommendation item has at least one structured reason source
    - Developer trace can identify whether a bad result came from vision, styling rules, shopping, or LLM refinement

### ⬜ Step 33: Complete Frontend Release Gates
- Current flaw: Web and type-check validation pass, but manual device/simulator walkthroughs remain blocked by local tooling.
- Improve by:
    - Completing either physical-device Expo Go/dev-client validation or simulator validation
    - Capturing screenshots/videos for Home, Analysis, Results, warning, low-confidence, and no-products states
    - Testing real uploads against a running backend
    - Recording known platform-specific issues
- Suggested verification:
    - Manual walkthrough with real upload is marked complete
    - Device/platform notes are added to this tracker

---

## Portfolio Upgrade Sprint (July 2026) — Phases 0-2 complete

Executed against the approved upgrade plan (see git history from `Initial commit`).

### ✅ Phase 0: Foundation & vision rewrite
- git repo initialized (monorepo incl. frontend), GitHub Actions CI: ruff check + format, strict mypy (0 errors), pytest
- Vision pipeline rewritten: **one CLIP image pass per request** (was 4), process-cached text prompt embeddings, warm latency **~15s → 0.041s**
- Per-attribute confidences replace the meaningless 4-head average; `confidence` = clothing-type head
- BLIP captioning optional (`VISION_ENABLE_CAPTION`, default off — ~1GB model not loaded)
- `VisionResult` carries the L2-normalized CLIP embedding for downstream reuse (`ctx.metadata["image_embedding"]`)

### ✅ Phase 1: Evals as a real gate + observability
- Eval grid expanded 3 → **105 cases** (generated type×style grid + golden cases): structural metrics need no hand labels (empty-recommendation rate, complete-outfit rate, duplicates, intent mismatches, per-agent latency)
- Expanded grid immediately found a real bug: **8.6% empty-recommendation rate** in style-policy dead zones → fixed with structure-aware safe fallback → **0.0%**
- Product-relevance eval over 53 labeled products: keyword baseline **precision 0.74 / recall 0.96 / F1 0.84** (the number Phase 3's embedding reranker must beat)
- `--check` gates run in CI; `--record` persists `EvaluationRun` rows with git SHA
- Langfuse tracing: root span per analysis, agent-typed observations, LLM generations with token usage; disabled cleanly without keys

### ✅ Phase 2: LangGraph agentic core
- Orchestration rebuilt as a **StateGraph** with conditional edges; `Orchestrator` is now a façade (same API + SSE contract)
- **IntentAgent**: free-text `user_intent` → DeepSeek structured output → deterministically validated `StyleIntent` (occasion, budget, climate, styles, avoid/owned items); keyword-heuristic fallback without an API key
- Intent actually changes behavior: effective style drives the rule engine, avoid-list filters matches, owned items skip shopping, `wants_shopping=False` routes past the shopping node
- **VerifierAgent**: deterministic checks (outfit completeness, forbidden/duplicate items, budget vs. product prices, unsupported explanation claims) + optional LLM critic; fixable issues trigger **exactly one constraint-tightened rebuild** via a graph cycle
- Explanations are now **evidence-grounded**: each recommendation carries `evidence` (rule facts); the LLM words the explanation from those facts only (tone-refinement prompts deleted)
- Verified: same image with "office" vs "gym" intent produces different outfits; seeded policy violations are caught and rebuilt; 221 tests + eval gate green

### ✅ Phase 3: Embedding product reranking + digital wardrobe
- Product matching rebuilt on **zero-shot CLIP gates**: titles classified against the same catalog heads as the vision pipeline (type/color/gender must agree), survivors ranked by spec similarity + thumbnail image similarity (Redis-cached)
- Measured on 53 labeled products: **F1 0.893 vs keyword baseline 0.839** (precision 0.862 vs 0.743); honest finding recorded: naive spec-vs-title cosine alone scored *worse* than keywords (0.81)
- **Digital wardrobe**: garment uploads auto-tagged + embedded; tag-gated, embedding-ranked matching marks recommendation items `owned` (with `wardrobe_item_id`) so shopping only covers missing pieces; CRUD under `/api/v1/wardrobe/items` with manual tag correction
- **Deliberately no vector DB** (see `docs/adr/002`): per-request reranking is in-memory; wardrobe scale makes brute-force cosine the right call; pgvector documented as the scale-up
- Fresh-database schema fixed: backfill migration for analysis/feedback tables (original initial migration was empty), session rollback on persist failure
- Verified end-to-end on a live server: upload → tag correction → analysis marks owned items, live DeepSeek grounded explanations

### ✅ Phase 4: LLM-as-judge + admin metrics (multi-garment vision deferred)
- `evaluation/llm_judge.py`: calibration-gated judge (must separate hand-crafted good/bad pairs before scores count) for **explanation faithfulness** and **intent adherence**
- First judged run caught a real grounding bug — occasion cited in explanations but absent from evidence; fix measured: **faithfulness 0.5 → 1.0**
- `MetricsService` + `GET /api/v1/admin/metrics`: analyses (avg confidence, low-confidence rate), feedback like-rate, wardrobe size, eval-run history — verified live
- Multi-garment vision (OWLv2 detection) deferred: single-garment path degrades safely via confidence gating; tracked as follow-up

### 🟨 Phase 5: Trend RAG + virtual try-on MVP + auth hardening — pending
- Try-on requires a hosted diffusion API decision + key (fal.ai / Replicate, ~$0.03-0.10/image) — **user decision needed**
- Langfuse tracing is wired but needs cloud keys (free tier) to see real traces — **user signup needed**
- Auth hardening + trend RAG are unblocked next steps

### ✅ Phase 6: Portfolio packaging (GitHub publish still needs user auth)
- README rewritten: architecture (mermaid), measured before/after table, honest findings, run instructions
- ADRs in `docs/adr/`: 001 LangGraph, 002 no-vector-DB-yet, 003 LLM-proposes-rules-verify, 004 model choices
- Frontend aligned: styling-request input on Home, My Wardrobe screen (add/fix-tags/remove), "In your wardrobe" badges + "Why this look" evidence viewer on Results, full graph stage list on Analysis (planner-skipped stages drop away); `tsc --noEmit` clean, web export bundles
- `HANDOFF.md` added: before/after change log + pre-testing checklist
- **GitHub publish blocked on `gh` auth** (user action)

---

## Key Files Quick Reference

| What | File | Key exports |
|---|---|---|
| App factory | `backend/app.py` | `create_app()` |
| Settings | `backend/core/config.py` | `Settings`, `get_settings()` |
| DI container | `backend/core/dependencies.py` | `get_vision_service()`, `get_llm_service()`, `get_memory_service()`, `get_feedback_service()`, `get_product_search_service()`, `get_product_search_tool()`, `get_orchestrator()` |
| Clothing enums | `backend/schemas/clothing.py` | `ClothingType`, `Color`, `Pattern`, `Style`, `ClothingAttributes` |
| API schemas | `backend/schemas/api.py` | `AnalysisResponse`, `Recommendation`, `RecommendationItem`, `ProductLink`, `Gender`, `ShoppingIntent` |
| Vision pipeline | `backend/services/vision.py` | `VisionService` |
| LLM service | `backend/services/llm.py` | `LLMService` |
| Memory service | `backend/services/memory.py` | `MemoryService`, `UserPreferences` |
| Product search | `backend/services/product_search.py` | `ProductSearchService` |
| Feedback service | `backend/services/feedback.py` | `FeedbackService` |
| Agent base | `backend/agents/base.py` | `BaseAgent`, `AgentContext`, `StyleMatch`, `AgentState` |
| Vision agent | `backend/agents/vision_agent.py` | `VisionAgent` |
| Styling agent | `backend/agents/styling_agent.py` | `StylingAgent` (delegates to tools, re-exports rule tables) |
| Color tool | `backend/tools/color_matcher.py` | `ColorMatcherTool`, `COLOR_COMPLEMENTS` |
| Style tool | `backend/tools/style_rules.py` | `StyleRuleEngineTool`, `ITEM_PAIRINGS`, `STYLE_COMPATIBILITY`, `PATTERN_PAIRS` |
| Product tool | `backend/tools/product_search.py` | `ProductSearchTool` (Redis cache + SerpAPI) |
| Recommendation agent | `backend/agents/recommendation_agent.py` | `RecommendationAgent` (accepts optional `LLMService`) |
| Orchestrator | `backend/agents/orchestrator.py` | `Orchestrator` — `run()` + `run_stream()` (accepts optional `LLMService`, `MemoryService`, `ProductSearchTool`) |
| Shopping agent | `backend/agents/shopping_agent.py` | `ShoppingAgent` (attaches `ProductLink` to items via `ProductSearchTool`) |
| Analysis route | `backend/api/routes/analysis.py` | `POST /api/v1/analyze` (uses Orchestrator + FeedbackService for DB persistence) |
| Stream route | `backend/api/routes/stream.py` | `POST /api/v1/analyze/stream` (SSE streaming via `sse-starlette`) |
| Feedback route | `backend/api/routes/feedback.py` | `POST /api/v1/feedback` (FeedbackService + DB + Redis memory) |
| ORM models | `backend/models/records.py` | `AnalysisRecord`, `FeedbackRecord` |

---

## How to Continue

1. Read this file to understand current state
2. Pick the next ⬜ step from the list above
3. Implement it following the patterns established in completed steps
4. Run the relevant test to verify
5. **Update this file** — mark the step as ✅ and add verification notes

---

*Last updated: 9 July 2026 — Phases 0-4 + 6 complete (`226 passed`, eval gate green, strict mypy clean, frontend tsc clean). See `HANDOFF.md` for the testing checklist. Next: auth hardening, trend RAG, try-on decision, OWLv2 multi-garment.*
