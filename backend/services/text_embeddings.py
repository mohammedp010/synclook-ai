"""Text embedding service — BGE sentence embeddings for catalog retrieval.

CLIP's text tower is deliberately *not* reused here. It is trained to align
short captions with images, truncates at 77 tokens, and its text-text
similarities compress into a narrow band — fine for the zero-shot attribute
heads it already serves, poor as a retrieval index over product copy.
``BAAI/bge-small-en-v1.5`` is a retrieval-trained encoder: 384 dimensions,
~130MB, and fast enough on CPU that catalog queries stay inline.

Two asymmetries matter and are modelled explicitly:

- **Queries vs documents.** BGE v1.5 is trained with a short instruction on
  the query side only; ``embed_query`` adds it, ``embed_documents`` does not.
- **Pooling.** BGE pools the CLS token, not the mean of the sequence. Mean
  pooling silently degrades recall, so it is spelled out here rather than
  inherited from a helper library.

Inference shares the vision module's thread pool: the process should never
run more model forward passes concurrently than that pool allows, whichever
model they belong to.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from threading import Lock

import torch
from transformers import AutoModel, AutoTokenizer, PreTrainedModel, PreTrainedTokenizerBase

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.services.vision import _inference_pool

logger = get_logger(__name__)

# BGE v1.5 retrieval instruction. Applied to queries only — the model card is
# explicit that documents must be embedded bare, and prefixing both sides
# measurably hurts.
_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

# Product copy is short; 256 tokens covers title + brand + description with
# room to spare and keeps batches cheap.
_MAX_TOKENS = 256


class _TextModelHolder:
    """Lazy-loaded singleton for the BGE encoder and its tokenizer."""

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
                name = get_settings().text_embedding_model_name
                logger.info("loading_text_embedding_model", model=name)
                self._tokenizer = AutoTokenizer.from_pretrained(name)
                model = AutoModel.from_pretrained(name)
                model.to(self.device)
                model.eval()
                self._model = model
                logger.info("text_embedding_model_loaded", model=name)
        assert self._model is not None and self._tokenizer is not None
        return self._model, self._tokenizer


@lru_cache
def _get_text_model() -> _TextModelHolder:
    return _TextModelHolder()


def _encode_sync(texts: list[str]) -> list[list[float]]:
    """Encode texts into normalized CLS-pooled embeddings (one forward pass)."""
    holder = _get_text_model()
    model, tokenizer = holder.model

    batch = tokenizer(
        texts,
        padding=True,
        truncation=True,
        max_length=_MAX_TOKENS,
        return_tensors="pt",
    )
    batch = {k: v.to(holder.device) for k, v in batch.items()}

    with torch.no_grad():
        hidden = model(**batch).last_hidden_state

    # CLS pooling, then L2 normalization so cosine similarity is a dot product
    # and pgvector's `<=>` operator is directly comparable across rows.
    pooled = hidden[:, 0]
    normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)
    return [row.tolist() for row in normalized.cpu()]


class TextEmbeddingService:
    """Async wrapper around the BGE encoder.

    Stateless and cheap to construct; the model itself is a process-wide
    singleton, so instances can be created freely.
    """

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed catalog-side text. No instruction prefix (see module docs)."""
        if not texts:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_inference_pool, _encode_sync, texts)

    async def embed_document(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]

    async def embed_query(self, query: str) -> list[float]:
        """Embed a search query, with the retrieval instruction prefix."""
        return (await self.embed_documents([_QUERY_INSTRUCTION + query]))[0]
