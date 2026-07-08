# ADR 002: No vector database (yet) — embeddings without the infrastructure

**Status**: accepted (July 2026)

## Context

The system uses CLIP embeddings in three places: classifying uploads, gating/ranking shopping
products, and matching recommendations against the user's wardrobe. The reflexive architecture
would add a vector database (pgvector / Qdrant / Weaviate). We asked where similarity search
actually has scale.

## Decision

No vector store at all, for now:

- **Product reranking** operates on the handful of SerpAPI results for the current request.
  Embedding them in memory and ranking against the request's spec embedding is a matrix multiply;
  persisting them would add infrastructure to make the problem slower. Thumbnail embeddings are
  cached in Redis by URL because they repeat across requests.
- **Wardrobe matching** searches one user's closet — realistically tens to hundreds of items.
  Brute-force cosine over an embedding column (JSONB) is microseconds and has zero operational
  cost. An index only pays for itself at ~10⁵+ vectors.

The documented scale-up path, if a product *catalog* (millions of items) is ever ingested:
pgvector on the existing PostgreSQL (`CREATE EXTENSION vector`, migrate the column, add HNSW) —
chosen over a standalone vector DB because the operational surface stays one database.

## Consequences

- Zero new infrastructure; the embedding work shipped in days.
- The wardrobe schema keeps the embedding column explicit, so the pgvector migration is a column
  type change, not a redesign.
- Interview-honest answer to "why no vector DB?": *measured the corpus size first.*
