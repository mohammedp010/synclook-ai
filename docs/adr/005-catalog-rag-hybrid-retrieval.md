# ADR 005: Catalog RAG — pgvector, hybrid retrieval, cross-encoder rerank

**Status**: accepted (September 2026). Supersedes [ADR 002](002-no-vector-database-yet.md)
for the product catalog only; the wardrobe still scans in Python, for the reasons ADR 002 gives.

## Context

Shopping links came exclusively from a live provider search: one SerpAPI call per outfit slot,
whatever came back, filtered by zero-shot gates. That has three problems a portfolio project
should not ship with:

- **It is not reproducible.** The same image can produce different products on two consecutive
  runs, so retrieval quality cannot be measured, only sampled.
- **Recall is whatever the provider felt like returning.** With `shopping_results_per_item=2`
  a strict gate frequently leaves a slot empty — not because nothing suitable exists, but
  because two candidates is a thin sample.
- **Every request costs an API credit and ~8s of latency**, on the request path.

ADR 002 declined a vector database after measuring the corpora then in play (a handful of live
results, a few hundred wardrobe items). It named the condition that would change the answer:
"if a product *catalog* is ever ingested". This is that.

## Decision

Ingest a product corpus into PostgreSQL and retrieve from it before calling the provider.

**pgvector, not a standalone vector database.** The corpus is thousands of rows, not millions,
and it needs to be filtered by clothing type, gender and price — attributes that already live in
PostgreSQL. Keeping vectors in the same database means those are `WHERE` clauses rather than a
two-system join, and the operational surface stays one database. This is the scale-up path ADR
002 wrote down, taken as written.

**HNSW, not IVFFlat.** IVFFlat trains its lists on a sample of existing rows, so its recall
degrades on a catalog that starts empty and grows by ingestion. HNSW builds incrementally.

**Hybrid retrieval, fused by RRF.** Two arms run over the same filtered candidate set:
PostgreSQL full-text (exact on brands and model numbers, where embeddings blur — "Levi's 511"
and "Levi's 501" are near-identical vectors) and BGE embeddings over pgvector (robust to
phrasing the corpus never uses literally). `ts_rank_cd` is unbounded and corpus-dependent while
cosine is `[-1, 1]`, so the scores cannot be added; Reciprocal Rank Fusion reads only the ranks
and needs no per-corpus normalization.

**BGE for retrieval, not CLIP's text tower.** CLIP is kept for everything it already does. Its
text encoder is trained to align short captions with images, caps at 77 tokens, and compresses
text-text similarity into a narrow band — the wrong tool for a search index.
`BAAI/bge-small-en-v1.5` is retrieval-trained, 384-dim and ~130MB.

**A cross-encoder reranks the shortlist.** Retrieval is a bi-encoder problem: query and document
never meet, so the model compares compressed summaries. A cross-encoder reads the pair jointly.
It costs one forward pass per candidate, so it only ever sees the top ~20.
`cross-encoder/ms-marco-MiniLM-L-6-v2` (~90MB) is the default over `BAAI/bge-reranker-base`
(~1.1GB, multilingual) because the corpus is English product copy and the demo runs on a laptop;
the heavier model is a `RERANKER_MODEL_NAME` away.

**The catalog does not replace live search — it precedes it.** Slots the corpus cannot fill still
go to the provider and through the existing zero-shot gates.

## Measured

Ten labelled queries against a 53-product corpus (`evaluation/catalog_retrieval.py`), at k=3.
"Retrieval only" removes the clothing-type and gender filters so the retriever, rather than the
taxonomy, has to do the work:

| Arm | recall@3 (filtered) | recall@3 (retrieval only) | precision@3 (retrieval only) |
|---|---|---|---|
| lexical  | 0.741 | 0.630 | 0.567 |
| semantic | 0.815 | 0.815 | 0.733 |
| hybrid (RRF) | 0.852 | 0.778 | 0.700 |
| **hybrid + rerank** | **0.852** | **0.852** | **0.767** |

Two honest readings of this table:

- **Fusion alone loses to the semantic arm once the taxonomy filter is removed** (0.778 vs
  0.815). On short product titles the lexical arm is weak — a title and an outfit spec share few
  exact terms — and RRF drags the stronger arm toward the weaker one. With the production filters
  on, where the candidate pool is already narrow, fusion is ahead (0.852 vs 0.815); the ordering
  reverses depending on how much work the filters do, which is exactly why the eval reports both.
  The cross-encoder wins under either setting, which is why the lexical arm stays: it costs
  recall only until something reads the pairs properly.
- **53 rows is a small corpus and 10 queries is a small query set.** These numbers order the
  arms; they do not establish absolute quality, and the lexical arm's case (exact brand and
  model matching) is precisely the case a 53-row corpus cannot exercise.

Relevance is labelled per case, so a product that would genuinely suit a different case's query
counts as a miss there. Every figure above is a lower bound.

## Consequences

- Shopping results for covered slots are reproducible, free, and off the network path.
- New failure modes are all soft: no corpus, no PostgreSQL, or no reranker each degrade to the
  previous behaviour rather than an error.
- Ingestion is now a thing that must be run and kept fresh (`last_seen_at`, `in_stock`). It is a
  cron job that does not exist yet — for now it is run by hand. Since 2026-09-13 there is
  something to run: `catalog_ingest --refresh` re-queries the slots the corpus already holds,
  upserts what still comes back, and demotes what does not. Demotion is deliberately conservative
  — absence from one provider search is not proof a product is gone, so a row must *also* have
  gone unconfirmed past `catalog_stale_after_days` before it is marked out of stock. Retrieval
  additionally refuses rows outside that window, so a corpus nobody refreshes ages out into live
  search instead of serving stock claims it cannot support.
- CI grew a `pgvector/pgvector:pg16` service, because index behaviour and full-text ranking are
  exactly what the retrieval eval measures and mocking them would measure nothing.
- Two more models load on a cold start (~220MB combined). Both are lazy and neither is on the
  path of a request that does not shop.
