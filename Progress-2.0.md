# Synclook AI 2.0 - AI Feature Roadmap

> Purpose: Track future-facing product features that make Synclook feel like a modern AI fashion platform, not only a rule-based outfit recommender. Keep current flaw fixes in `Progress.md`; use this file for new feature expansion.

---

## 2.0 Direction

Synclook 2.0 should evolve from:

```
single uploaded item -> rule-based outfit suggestions -> shopping links
```

to:

```
multimodal user intent + wardrobe + catalog intelligence
    -> planned outfit strategy
    -> grounded retrieval and verification
    -> complete looks, fit guidance, try-on, and shopping automation
```

The strongest portfolio signal is not "more LLM text." It is a measurable AI system that combines vision, retrieval, personalization, agents, evaluation, and user-facing product value.

---

## Feature Themes

### 1. Conversational Multimodal Stylist

**Goal:** Let users upload an image and ask for specific styling help in natural language.

Example prompts:
- "Style this for a rainy dinner under INR 5000."
- "Make this more streetwear but office-safe."
- "I already own white sneakers and a black jacket. Use those if possible."

AI skills demonstrated:
- Multimodal input handling
- Intent extraction
- Constraint parsing
- Agent planning
- Grounded recommendation generation

Implementation notes:
- Add `user_intent` text to `/analyze` and `/analyze/stream`
- Add an `IntentAgent` before styling
- Extract occasion, budget, climate, preferred fit, dress code, avoid list, owned items, and shopping intent
- Store parsed intent in `AgentContext.metadata`
- Use the LLM for structured extraction, then deterministic validation

Suggested acceptance criteria:
- Same image can produce meaningfully different recommendations for office, date night, gym, wedding, and travel intents
- Invalid or conflicting requests return a graceful clarification or safe fallback
- Parsed constraints are visible in debug/evaluation output

---

### 2. Wardrobe Memory / Digital Closet

**Goal:** Let users scan or upload their owned clothing items and generate outfits from their wardrobe before shopping.

AI skills demonstrated:
- Persistent personalization
- Image attribute extraction at scale
- Embedding search
- User modeling
- Retrieval-augmented recommendations

Core features:
- Wardrobe item upload
- Automatic tagging: item type, color, pattern, style, season, formality
- Manual correction flow for tags
- "Use my wardrobe first" recommendation mode
- Missing-piece detection
- Outfit history and repeat avoidance

Suggested backend additions:
- `WardrobeItem` ORM model
- `WardrobeService`
- `WardrobeAgent`
- Image/text embedding column or vector store
- API routes:
    - `POST /api/v1/wardrobe/items`
    - `GET /api/v1/wardrobe/items`
    - `PATCH /api/v1/wardrobe/items/{id}`
    - `DELETE /api/v1/wardrobe/items/{id}`

Suggested acceptance criteria:
- Recommendations prefer owned items when compatible
- Shopping is used only for missing categories when wardrobe mode is enabled
- User corrections improve future recommendations

---

### 3. Product Catalog RAG and Reranking

**Goal:** Replace fragile live shopping title matching with a grounded product retrieval pipeline.

AI skills demonstrated:
- Retrieval augmented generation
- Vector search
- Hybrid search
- Reranking
- Product matching evaluation

Core features:
- Product ingestion from SerpAPI or curated CSV/API feeds
- Product text normalization
- Product image embedding
- Product text embedding
- Hybrid retrieval: keyword + vector search
- Reranker for item type, gender/shopping intent, color, price, availability, and style
- Product evidence shown to the user

Suggested backend additions:
- `ProductCatalogService`
- `ProductIngestionJob`
- `ProductRetrievalAgent`
- Optional vector DB: pgvector, Qdrant, Weaviate, or Chroma
- Product quality score:
    - item type match
    - color match
    - style match
    - price confidence
    - availability freshness
    - image similarity

Suggested acceptance criteria:
- Shopping mismatch rate is measured and lower than the current title-filter baseline
- Results include evidence for why each product matches
- Stale/out-of-stock products can be filtered or marked

---

### 4. Virtual Try-On MVP

**Goal:** Allow users to preview recommended products or outfit combinations on a person/photo.

AI skills demonstrated:
- Generative AI
- Image conditioning
- Computer vision preprocessing
- Safety and quality checks
- Visual UX integration

Scope options:
- MVP: generated preview from user garment + selected product image
- Safer MVP: product-on-mannequin or flat-lay outfit composition
- Advanced: person image + garment try-on

Implementation notes:
- Start with an explicit opt-in flow
- Store try-on outputs separately from normal analysis
- Add visible confidence/quality warning
- Add evaluation checks for blank outputs, body distortion, garment mismatch, and unsafe images

Suggested acceptance criteria:
- Generated previews are nonblank and clearly tied to selected products
- User can compare original recommendation vs try-on preview
- Low-quality generations fail safely

---

### 5. Fit and Size Recommender

**Goal:** Move from "this looks good" to "this is likely to fit you and your preferences."

AI skills demonstrated:
- Structured data reasoning
- Personalization
- Risk scoring
- Retrieval from size charts and reviews

Core features:
- User measurements or approximate profile
- Fit preference: slim, regular, relaxed, oversized
- Size chart parsing
- Brand-level size memory
- Return-risk score
- Recommendation labels:
    - "likely true to size"
    - "consider sizing up"
    - "low fit confidence"

Suggested backend additions:
- `UserFitProfile`
- `SizeChartService`
- `FitAgent`
- `fit_confidence` and `fit_reason` on `ProductLink` or a richer product schema

Suggested acceptance criteria:
- Products without useful size evidence are marked low-confidence
- Fit recommendation changes when user fit preference changes
- User feedback can update brand-level fit memory

---

### 6. Price / Budget Agent

**Goal:** Add practical shopping intelligence around budget, price drops, and alternatives.

AI skills demonstrated:
- Agentic tool use
- Monitoring
- Ranking under constraints
- User preference optimization

Core features:
- Budget-aware outfit generation
- Price comparison across stores
- Similar cheaper alternatives
- Price-drop watchlist
- "Complete this look under INR X"
- Cart-ready recommendation bundle

Suggested backend additions:
- `BudgetAgent`
- `PriceMonitorService`
- `Watchlist` ORM model
- Background job or scheduled task for price refresh

Suggested acceptance criteria:
- User can set a total outfit budget, not only item-level budget
- Recommendations include total estimated cost
- The system can find lower-cost alternatives without changing the outfit intent

---

### 7. Trend-Aware Recommendation Mode

**Goal:** Let users choose how trend-driven the recommendations should be.

AI skills demonstrated:
- Retrieval
- Grounded summarization
- Controlled generation
- Ranking with explicit style objectives

Modes:
- Classic
- Current
- Experimental

Core features:
- Trend source ingestion
- Seasonal trend tags
- Region-aware trend signals
- Explanation of why a look is classic/current/experimental
- Ability to disable trends for timeless recommendations

Suggested backend additions:
- `TrendIngestionService`
- `TrendKnowledgeBase`
- `TrendAgent`
- `trend_tags` and `trend_confidence` on recommendations

Suggested acceptance criteria:
- Same base item produces distinct classic/current/experimental outputs
- Trend claims are grounded in retrieved trend snippets or catalog evidence
- Trend mode never overrides hard outfit constraints

---

### 8. AI Evaluation and Observability Dashboard

**Goal:** Make model and agent quality visible, measurable, and defensible.

AI skills demonstrated:
- Evaluation design
- Observability
- Regression testing
- Production AI quality management

Dashboard metrics:
- Vision confidence distribution
- Low-confidence rate
- Invalid item rate
- Gender/shopping-intent mismatch rate
- Shopping product mismatch rate
- Empty recommendation rate
- LLM rewrite failure rate
- Latency by agent
- API cost by request
- Cache hit rate
- Feedback like/dislike rate
- Conversion proxy: product clicks

Suggested backend additions:
- `EvaluationRun` model
- `EvaluationCase` model or JSON fixtures
- `MetricsService`
- Admin/dashboard API route

Suggested frontend additions:
- Internal dashboard screen
- Evaluation run table
- Per-case failure inspection
- Agent trace viewer

Suggested acceptance criteria:
- Every major recommendation change can be evaluated before release
- Metrics are tracked over time
- Failures include enough trace data to debug quickly

---

### 9. Agent Trace and Recommendation Explanation Viewer

**Goal:** Show users and evaluators why a recommendation happened.

AI skills demonstrated:
- Explainable AI
- Agent orchestration
- Grounded reasoning
- Debuggable product UX

Core features:
- User-facing short explanation
- Developer-facing full trace
- Rule hits and rejected candidates
- Retrieved wardrobe/product evidence
- LLM rewrite status
- Verifier result

Suggested additions:
- `ctx.metadata["trace"]`
- `TraceEvent` schema
- Optional `include_trace=true` query param for dev/admin use

Suggested acceptance criteria:
- A bad recommendation can be traced to vision, rule, retrieval, or shopping failure
- User-facing explanations remain short and non-technical
- Developer traces are available in tests and evaluation reports

---

### 10. Recommendation Verifier / Critic Agent

**Goal:** Add a final AI quality gate before returning recommendations.

AI skills demonstrated:
- Multi-agent verification
- Guardrails
- Structured critique
- Self-correction loop

Verifier checks:
- Complete outfit structure
- No forbidden items
- Occasion compatibility
- Budget compatibility
- Product/title/image relevance
- Duplicate or near-duplicate looks
- Explanation does not claim unsupported facts

Suggested backend additions:
- `VerifierAgent`
- `RecommendationIssue` schema
- Retry once with corrected constraints when issues are fixable

Suggested acceptance criteria:
- Known bad outputs are caught before reaching the UI
- Verifier decisions are recorded in traces
- The verifier cannot invent new outfit facts without structured changes

---

## Suggested 2.0 Build Order

1. Conversational multimodal intent
2. Wardrobe memory / digital closet
3. Product catalog RAG and reranking
4. AI evaluation and observability dashboard
5. Fit and size recommender
6. Price / budget agent
7. Recommendation verifier / critic agent
8. Trend-aware recommendation mode
9. Virtual try-on MVP
10. Agent trace and explanation viewer

---

## Notes From Current Industry Direction

- Modern fashion AI products increasingly combine visual search, personalization, product catalogs, and shopping assistance.
- Virtual try-on and product visualization are becoming common differentiators in AI shopping.
- Agentic commerce patterns are moving toward budget-aware search, product comparison, price monitoring, and cart assistance.
- For portfolio value, the most impressive signal is a system with retrieval, personalization, evals, observability, and grounded explanations rather than an LLM-only wrapper.

---

*Created: 2 July 2026*
