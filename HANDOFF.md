# Synclook AI — Upgrade Handoff

> What existed before, everything that was added/improved/fixed (July 8–9, 2026, 16 commits),
> and exactly what you need to do before testing. Companion docs: [README.md](README.md) (recruiter-facing),
> [docs/adr/](docs/adr/) (design decisions), [Progress.md](Progress.md) (step tracker).

---

## 1. What existed before

The state as of Step 29 (July 2, 2026):

- A **fixed sequential pipeline** presented as "multi-agent": `Orchestrator` looped over
  Vision → Styling → Recommendation → Shopping. No routing, no planning, no cycles.
- **LLM used only for "tone refinement"** — DeepSeek rewrote template sentences without being
  allowed to change anything. Cost and latency for functionally identical output.
- **Vision ran 4 full CLIP forward passes per image** (type/color/pattern/style heads each
  re-encoded the image) plus an unconditional ~1GB BLIP caption pass whose output was usually
  hidden as irrelevant. ~15s per request. The `confidence` field averaged four unrelated
  softmaxes into a meaningless number.
- **CLIP embeddings were computed and thrown away** while product matching used hand-maintained
  keyword/synonym tables and negative tokens (`-blouse -women`).
- **Personalization** was a ±0.05 score nudge on exact color matches from Redis.
- **Evals**: 3 fixtures reporting 0.0 error rates; fixtures had previously been edited to make
  new outputs pass.
- **No observability** (no tracing, no cost/latency visibility), **no CI**, and —
  critically — **the project was not a git repository**.
- Frontend (Expo) with Home/Analysis/Results screens, SSE streaming, shopping-intent pills.

What was already good and was kept: the FastAPI structure, DI container, graceful-fallback
philosophy, SSE contract, rule tables (repurposed as guardrails), Redis memory, Docker setup,
and the frontend design system.

---

## 2. What was added / improved / fixed

### Foundation (commits `fe3b6a1`…`3257485`)
| Change | Detail |
|---|---|
| **git + GitHub Actions CI** | Repo initialized (monorepo incl. frontend); CI runs ruff check, ruff format check, strict mypy, pytest, and the eval gate. HuggingFace model dir cached. |
| **Lint/type debt cleared** | 100 ruff errors → 0; 28 strict-mypy errors → 0 (still 0 across 54 source files). `poetry.lock` now committed. |

### Vision pipeline rewrite (`c7571fd`)
| Change | Detail |
|---|---|
| **~15s → 0.041s warm latency** | One CLIP image encoding per request shared across all four heads; constant text-prompt embeddings computed once per process. |
| **Meaningful confidence** | Per-head confidences (`color_confidence` etc.); `confidence` now = clothing-type head, which is what gates the low-confidence fallback. |
| **BLIP optional** | `VISION_ENABLE_CAPTION=false` by default — the ~1GB captioning model isn't even loaded. |
| **Embedding reuse** | The normalized CLIP image embedding rides along in `ctx.metadata` for retrieval/ranking downstream. |

### Evals became real (`58c1f97`, `833c0c8`)
| Change | Detail |
|---|---|
| **105-case eval grid** | Generated type×style grid + golden cases; structural metrics need no hand labels (empty-rate, outfit completeness, duplicates, intent violations, per-agent latency). |
| **Found + fixed a real bug** | The grid exposed an **8.6% empty-recommendation rate** (style-policy dead zones, e.g. sporty blazer). Fixed with structure-aware safe fallback → **0.0%**. |
| **Product-relevance eval** | 53 hand-labeled products; keyword baseline measured at P 0.743 / R 0.963 / F1 0.839. |
| **CI gate + history** | `harness.py --check` fails CI on regression; `--record` persists runs (git SHA + metrics) to PostgreSQL. |

### Observability (`696e53e`)
Langfuse tracing: one trace per analysis, an agent-typed span per graph node with elapsed time,
one generation per DeepSeek call with token usage. No-ops cleanly when keys are absent.

### The agentic core (`a376e0e`, `2d8f243`)
| Change | Detail |
|---|---|
| **LangGraph StateGraph** | intent → vision → styling → recommendation → [wardrobe] → [shopping] → verifier, with conditional edges. `Orchestrator` is now a façade; REST/SSE contracts unchanged. |
| **Real intent** | Free-text `user_intent` ("rainy dinner under ₹5,000") → DeepSeek structured output → deterministically validated `StyleIntent` (occasion, budget, climate, styles, avoid/owned items). Keyword-heuristic fallback without an API key. |
| **Intent changes behavior** | Preferred style drives the rule engine, avoid list filters matches, owned items skip shopping, "no shopping" routes past the shopping node entirely. Tested: office vs gym intents produce different outfits from the same image. |
| **VerifierAgent + retry cycle** | Deterministic checks (outfit completeness, forbidden/duplicate items, budget vs product prices, unsupported explanation claims) + optional LLM critic. Fixable findings trigger **exactly one** constraint-tightened rebuild — a graph cycle. |
| **Grounded explanations** | Each recommendation carries `evidence` (rule facts); the LLM words the explanation from those facts only. Tone-refinement prompts deleted. |

### Embedding retrieval & ranking (`ddef0d9`)
| Change | Detail |
|---|---|
| **Zero-shot product gates** | Product titles are classified against the *same* CLIP heads as images (type/color/gender must agree), then ranked by spec similarity + thumbnail similarity (Redis-cached). Measured: **F1 0.893 vs 0.839, precision 0.862 vs 0.743**. Keyword matcher kept behind `SHOPPING_MATCHER=keyword` for comparison. |
| **Honest negative result recorded** | Plain cosine similarity alone scored *worse* than keywords (F1 0.81) — documented in README/ADR. |

### Digital wardrobe (`4f997d4`)
Upload garment photos → auto-tagged by the vision pipeline + stored with CLIP embeddings →
recommendations mark items you already own (`owned`, `wardrobe_item_id`) → shopping only covers
missing pieces. CRUD at `/api/v1/wardrobe/items`; manual tag corrections supported. Deliberately
**no vector DB** (see [ADR 002](docs/adr/002-no-vector-database-yet.md)).

### Bugs found by live end-to-end testing (`9ed7bcb`)
- Fresh databases were missing `analysis_records`/`feedback_records` — the original alembic
  migration had been generated empty. New backfill migration fixes clean installs.
- A failed analysis persist left the DB session unusable (PendingRollbackError). Route now
  rolls back explicitly.

### LLM-as-judge + metrics (`bfd0e46`)
- Calibration-gated judge for **explanation faithfulness** and **intent adherence** — scores are
  withheld unless the judge first separates hand-crafted good/bad pairs.
- Its first run caught a real grounding bug (occasion cited but not in evidence);
  fix measured **faithfulness 0.5 → 1.0**.
- `GET /api/v1/admin/metrics`: analyses (avg confidence, low-confidence rate), feedback
  like-rate, wardrobe size, eval-run history.

### Docs (`146b029`) & frontend (`a48491b`)
- README with architecture diagram + measured results table; 4 ADRs.
- Frontend: **styling-request text input** on Home, **My Wardrobe** screen (add/fix-tags/remove),
  **"In your wardrobe" badges** and an expandable **"Why this look"** evidence viewer on Results,
  full pipeline stage list on the Analysis screen (planner-skipped stages drop away).
  Verified: `tsc --noEmit` clean, web export bundles.

### Environment repair + live shopping fix (Phase A, `1cc357e`)
- **`transformers` v5 broke CLIP pooling** — `.pooler_output` on the text tower returns the
  pre-projection state in v5. Every text embedding was silently the wrong tensor. Pinned and
  corrected; the zero-shot heads were re-measured afterwards, not assumed.
- **Live shopping returned zero products** — the CLIP text↔image similarity gate compared raw
  cosine (which lives in a ~0.2–0.35 band across modalities) against a 0.75 threshold, so real
  provider results were always rejected. Fixture thumbnails were fake, which is why the tests
  never caught it. Gate now scores on the same taxonomy heads the vision pipeline uses.
- **Thumbnail fetches were missing a user-agent** — Wikimedia and several retail CDNs answer 403
  to the default httpx UA, so those thumbnails silently never embedded. Affects the live shopping
  path, not just ingestion.

### Product catalog RAG (Phase B, `8914a4e`)
- **pgvector 0.8.0** compiled against `postgresql@15`; migration `c3f81a2b7d64` adds
  `product_catalog_items` with a 384-dim BGE text vector, a 512-dim CLIP image vector, HNSW
  cosine indexes on both, and a `GENERATED ALWAYS` tsvector (title/brand weighted above
  description) behind a GIN index.
- **Hybrid retrieval** (`backend/services/product_catalog.py`) — BM25-style lexical arm +
  vector arm fused with Reciprocal Rank Fusion (k=60), then reranked by a
  `ms-marco-MiniLM-L-6-v2` cross-encoder whose sigmoid output is a calibrated relevance
  probability; `catalog_min_score=0.5` was set from measured scores, not guessed.
- **Ingestion job** (`python -m backend.jobs.catalog_ingest`) — a type×gender query grid, price
  parsing, dedup, taxonomy classification, a coarse image veto (upper body / lower body / feet /
  accessory — the granularity CLIP can actually support), and `--export` / `--from-file` so a
  catalog can be rebuilt without spending SerpAPI credits.
- **ShoppingAgent retrieves before it searches** — catalog first, live provider only for slots
  the catalog could not fill. Falls back completely and silently if PostgreSQL is unreachable.
- **New eval** `evaluation/catalog_retrieval.py`: recall@k / precision@k / MRR across four arms,
  reported with taxonomy filters both on and off. Measured at k=3, filters off: lexical 0.630,
  semantic 0.815, hybrid RRF 0.778, hybrid+rerank **0.852**. The RRF regression is real and is
  written up in [ADR 005](docs/adr/005-catalog-rag-hybrid-retrieval.md).
- CI now runs a `pgvector/pgvector:pg16` service container, applies migrations, and runs the
  retrieval eval.

### Eval history + quality dashboard (Phase C, `0d8376a`)
- **The intent-adherence judge was measuring nothing.** Every sampled case was scored against a
  hardcoded `"office day"`, so gym and beach looks were counted as failures and the metric sat at
  0.667 regardless of system behaviour. `evaluation/llm_judge.py` now rotates one natural-language
  request per recognised occasion through the real `IntentAgent` → `StylingAgent` →
  `RecommendationAgent` path and judges against the occasion the system itself extracted.
- **That fix immediately caught a production bug.** The LLM sometimes returns
  `occasion='wedding'` with `preferred_styles=[]`; styling then fell back to the *detected
  garment's* style, so a wedding request produced smart-casual jeans. `intent_agent` now backfills
  the style an occasion implies from the same keyword table the heuristic extractor uses
  (`style_lean_for_occasion`). Wedding → formal, jeans → trousers. Adherence **0.667 → 0.875**.
- **`evaluation_runs` is now shared history.** `EvaluationRun` gained a `suite` column (migration
  `d7a41e60b9c2`) and `evaluation/recording.py` centralises best-effort recording; all four suites
  take `--record`. Recording never fails a run — a broken database loses history, not results.
- **`GET /api/v1/admin/dashboard`** — one self-contained HTML template (no CDN, no charting
  library) over `/admin/metrics`: system counters plus, per suite, hand-drawn SVG sparklines for
  metrics that moved and a compact table for those that did not.
- 289 tests. Ruff and strict mypy clean; mypy in CI now covers `evaluation/` too, which needed
  `evaluation/__init__.py` and a typed `CalibrationCase`.

### Retrieval evidence in the UI (2026-09-13)
- Products now explain themselves the way looks do. Each product carries
  `match_evidence` — which arm retrieved it and at what rank, whether the arms agreed, and the
  cross-encoder score (or the fusion rank, when the reranker is unavailable).
- **What you'll see:** a `% relevant` line on each product card, and a **"Why these products"**
  toggle under each outfit slot's product row. Catalog hits show retrieval ranks; live-search
  products show their zero-shot gate facts.
- No eval metric moved, and none should have — retrieval order is unchanged; this only stops
  discarding the reasons for it.

### Availability freshness (2026-09-13)
- **New:** `poetry run python -m backend.jobs.catalog_ingest --refresh --max-queries 10`.
  It re-queries the slots already in the catalog, refreshes price/copy/`last_seen_at` for whatever
  still comes back, and marks the rest out of stock. **One SerpAPI credit per slot** — `--max-queries`
  is the budget cap.
- Retrieval now ignores rows last confirmed more than `CATALOG_STALE_AFTER_DAYS` days ago
  (default 30; set 0 to disable). A stale corpus falls back to live search rather than serving
  stock claims nobody has verified.
- Products carry a `Stock confirmed N days ago` line in their evidence, so "in stock" reads as a
  dated observation.
- Retrieval quality is unchanged — recall@3 reproduces the baseline exactly (0.630 / 0.815 /
  0.778 / 0.852).

### Update: the catalog now has a real corpus
- The `SERPAPI_API_KEY` truncation issue is fixed — `.env` now holds a valid 64-character key.
  A real `--grid` ingest has run: `product_catalog_items` holds **5 rows** (`source='serpapi'`),
  exported to `data/catalog_seed.json` so the corpus can be rebuilt for free from here on. The
  0.852 recall figure is still measured from the eval's own temporary `source='eval'` rows, not
  this corpus — 5 products is too small a base for a meaningful retrieval eval. Growing the real
  corpus (`catalog_ingest --grid --max-queries N --export data/catalog_seed.json`) is worth doing
  before trusting shopping results against it end-to-end.

### Still open after Phase C
- ~~**No occasion-specific colour policy.**~~ Re-measured 2026-09-13 before building it: a judged
  run scored faithfulness 1.0 / adherence 1.0 with zero misses, and a deterministic sweep of all
  105 eval cases through *"going to a wedding"* produced **0 all-white looks** (per-slot colour
  rotation already forces a non-white anchor). The Phase C miss was sample-dependent. No rule was
  written — details and the reproducer in [Progress.md](Progress.md) under *Open items*.

---

## 3. What YOU need to do before testing

### Required (10 minutes)

1. **Start PostgreSQL and Redis** (both Homebrew services):
   ```bash
   brew services start postgresql@15
   brew services start redis
   ```
   The `synclook` database already exists with all migrations applied. On any other machine:
   `createdb synclook && poetry run alembic upgrade head`.

2. **Check your `.env`** (already mostly set up — verify these):
   - `DEEPSEEK_API_KEY` — already present and working (intent extraction, grounded
     explanations, verifier critic, LLM judge). Without it everything still runs
     deterministically, but the headline LLM features fall back.
   - `SERPAPI_API_KEY` — set it if you want real product links; without it the shopping stage
     is skipped by the planner (that's expected behavior, not a bug).
   - `DATABASE_URL=postgresql+asyncpg://mohd@localhost:5432/synclook`
   - Catalog retrieval needs no key, but it does need the pgvector migration applied:
     `poetry run alembic upgrade head`. With an empty catalog it is a no-op.

3. **Start the backend**:
   ```bash
   cd /Users/mohd/styleforgeai
   export PATH="$HOME/.local/bin:$PATH"
   poetry run uvicorn main:app --reload
   ```
   First request loads CLIP (~5s cold); after that analysis is fast.

4. **Start the frontend** (web is the quickest check):
   ```bash
   cd frontend && npx expo start --web
   ```
   For a phone via Expo Go, set the API host first:
   `EXPO_PUBLIC_API_BASE_URL=http://<your-mac-LAN-IP>:8000 npx expo start`

### Suggested test flows

1. **Intent changes the outfit** — upload the same garment photo twice: once with styling request
   *"for the office"*, once with *"for the gym"*. The detected style badge and recommended items
   should differ; the Analysis screen should show the *intent* stage.
2. **Wardrobe loop** — Home → My Wardrobe → add 2–3 garment photos → fix any wrong tags →
   run an analysis. Matching items show the green **"In your wardrobe"** badge and no product cards.
3. **Evidence viewer** — on any result card, tap **"Why this look"** to see the rule facts;
   with your DeepSeek key on, the explanation above it should be fluent and cite only those facts.
4. **Planner routing** — set Product links "Off" (or write "no shopping links" in the request):
   the shopping stage should disappear from the Analysis screen.
5. **Quality tooling** (backend, optional):
   ```bash
   poetry run python -m pytest tests/ -q                    # 226 tests
   poetry run python evaluation/harness.py --check          # eval gate
   poetry run python evaluation/product_relevance.py        # both matchers A/B
   poetry run python evaluation/llm_judge.py --sample 6     # LLM judge (uses your key)
   curl localhost:8000/api/v1/admin/metrics                 # metrics endpoint
   ```

### Optional (unlocks more)

- **Langfuse tracing** — free account at https://cloud.langfuse.com → project keys →
  `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` in `.env`. Every analysis becomes an inspectable
  trace with per-agent latency and DeepSeek token usage. Great demo material.
- **Publish to GitHub** — `brew install gh && gh auth login`, then tell me and I'll create the
  repo and push (recommend starting private). A portfolio that isn't on GitHub doesn't exist.
- **Clean up test data** — my smoke tests left one analysis + one wardrobe item under user
  `demo-user`/`smoke-user`: `psql -d synclook -c "TRUNCATE analysis_records, wardrobe_items;"`
  if you want a clean slate. Also `frontend/.git.pre-monorepo-backup/` (the old nested repo's
  history) can be deleted whenever.

### Known gaps / not done yet (tracked)

- **No auth** — `user_id` is client-supplied (`demo-user` by default in the app). Fine for local
  testing; auth hardening is the next backend task.
- **Virtual try-on** — needs your decision on a paid diffusion API (fal.ai or Replicate,
  ~₹3–8/image) before I build it.
- **The catalog corpus is small** — a real ingest has run (5 rows, `data/catalog_seed.json`), but
  a 5-product corpus is too small to trust shopping results end-to-end. Growing it spends SerpAPI
  credits, so a bigger grid is yours to run: `poetry run python -m backend.jobs.catalog_ingest
  --grid --max-queries 20 --export data/catalog_seed.json`.
- **Trend-aware RAG mode** (catalog retrieval now exists; ranking by trend signal does not)
  and **multi-garment detection (OWLv2)** — designed, not yet built.
- **iOS/Android native builds** — web verified; simulator runs still need Xcode/Android SDK
  setup on this machine (pre-existing blocker from Step 24).
