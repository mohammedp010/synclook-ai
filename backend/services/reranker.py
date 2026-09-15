"""Cross-encoder reranking for catalog retrieval.

Retrieval (lexical + vector) is a *bi-encoder* problem: query and document are
embedded independently, so the model never sees them together and can only
compare compressed summaries. A cross-encoder reads the pair jointly and scores
the interaction directly, which is markedly more accurate — and far too
expensive to run over a whole catalog, since it costs one forward pass per
candidate. The standard arrangement, used here, is retrieve-then-rerank: a
cheap index proposes ~40 candidates, the cross-encoder reorders the top slice.

``cross-encoder/ms-marco-MiniLM-L-6-v2`` is the default: 6 layers, ~90MB, and
English-only, which matches a catalog of English product copy. Heavier
alternatives (``BAAI/bge-reranker-base``, ~1.1GB) are a config flip away via
``RERANKER_MODEL_NAME``; both expose a single-logit regression head, so the
code below is model-agnostic.

Reranking is an optimization, never a dependency: if the model cannot be
loaded, callers keep the retrieval order.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer, PreTrainedModel, PreTrainedTokenizerBase

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.services.vision import _inference_pool

logger = get_logger(__name__)

# Query + product title + brand comfortably fits; longer pairs are truncated
# from the document side, which is where the least discriminative text sits.
_MAX_TOKENS = 320

# Candidates per forward pass. Small enough to stay responsive on CPU, large
# enough that tokenization overhead is amortized.
_BATCH_SIZE = 16


@dataclass(frozen=True)
class RerankedCandidate:
    """A candidate's position in the input list and its relevance score."""

    index: int
    score: float


class _CrossEncoderHolder:
    """Lazy-loaded singleton for the cross-encoder and its tokenizer."""

    def __init__(self) -> None:
        self._model: PreTrainedModel | None = None
        self._tokenizer: PreTrainedTokenizerBase | None = None
        self._device: torch.device | None = None
        self._lock = Lock()

    @property
    def device(self) -> torch.device:
        if self._device is None:
            self._device = torch.device(get_settings().vision_device)
        return self._device

    @property
    def model(self) -> tuple[PreTrainedModel, PreTrainedTokenizerBase]:
        with self._lock:
            if self._model is None:
                name = get_settings().reranker_model_name
                logger.info("loading_reranker_model", model=name)
                self._tokenizer = AutoTokenizer.from_pretrained(name)
                model = AutoModelForSequenceClassification.from_pretrained(name)
                model.to(self.device)
                model.eval()
                self._model = model
                logger.info("reranker_model_loaded", model=name)
        assert self._model is not None and self._tokenizer is not None
        return self._model, self._tokenizer


@lru_cache
def _get_cross_encoder() -> _CrossEncoderHolder:
    return _CrossEncoderHolder()


def _score_sync(query: str, documents: list[str]) -> list[float]:
    """Score every (query, document) pair, batched."""
    holder = _get_cross_encoder()
    model, tokenizer = holder.model

    scores: list[float] = []
    for start in range(0, len(documents), _BATCH_SIZE):
        chunk = documents[start : start + _BATCH_SIZE]
        batch = tokenizer(
            [query] * len(chunk),
            chunk,
            padding=True,
            truncation="only_second",
            max_length=_MAX_TOKENS,
            return_tensors="pt",
        )
        batch = {k: v.to(holder.device) for k, v in batch.items()}

        with torch.no_grad():
            logits = model(**batch).logits

        # Both supported checkpoints train a single logit with binary
        # cross-entropy, so the sigmoid is a calibrated relevance probability —
        # a bounded, comparable number the rest of the pipeline can treat like
        # any other match score. The raw logit is unbounded and would not be.
        scores.extend(torch.sigmoid(logits.view(-1).float()).cpu().tolist())
    return scores


class RerankerService:
    """Async wrapper around the cross-encoder.

    Stateless and cheap to construct; the model is a process-wide singleton.
    """

    @property
    def enabled(self) -> bool:
        return get_settings().reranker_enabled

    async def rerank(self, query: str, documents: list[str]) -> list[RerankedCandidate]:
        """Reorder ``documents`` against ``query``, best first.

        Returns candidates carrying their original index. When reranking is
        disabled or the model is unavailable, the input order is returned
        unchanged with zero scores, so the caller's retrieval ranking survives.
        """
        if not documents:
            return []
        if not self.enabled:
            return _identity_order(documents)

        try:
            loop = asyncio.get_running_loop()
            scores = await loop.run_in_executor(_inference_pool, _score_sync, query, documents)
        except Exception as exc:  # pragma: no cover - depends on model availability
            logger.warning("rerank_failed", error=str(exc), candidates=len(documents))
            return _identity_order(documents)

        ranked = [RerankedCandidate(index=i, score=round(score, 4)) for i, score in enumerate(scores)]
        ranked.sort(key=lambda candidate: candidate.score, reverse=True)
        return ranked

    async def warmup(self) -> None:
        """Pre-load the cross-encoder so the first rerank is not a cold start."""
        if not self.enabled:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_inference_pool, lambda: _get_cross_encoder().model)
        logger.info("reranker_warmed_up", model=get_settings().reranker_model_name)


def _identity_order(documents: list[str]) -> list[RerankedCandidate]:
    return [RerankedCandidate(index=i, score=0.0) for i in range(len(documents))]
