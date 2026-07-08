# ADR 004: Model choices — local CLIP everywhere, DeepSeek for language

**Status**: accepted (July 2026)

## Context

The system needs (a) garment understanding from images, (b) similarity for retrieval/ranking,
(c) language reasoning. A portfolio project also has a hard budget constraint: near-zero
inference cost, no GPU assumption.

## Decision

**One local CLIP model (`openai/clip-vit-base-patch32`) serves every embedding need** — image
classification, product-title classification, spec similarity, wardrobe matching. This is the
load-bearing choice: because titles and images live in the same space as the classification
prompts, the *same zero-shot heads* classify both an uploaded photo and a product title
("one taxonomy, two modalities"). Warm cost per request is ~40 ms on CPU.

Efficiency contract (learned the hard way — the first implementation ran 4 full CLIP passes per
image and re-encoded constant prompts every request, ~15 s/request):

- one image encoding per request, shared across attribute heads
- text-prompt embeddings computed once per process
- BLIP captioning optional and off by default (~1 GB model for display-only metadata)

**DeepSeek (OpenAI-compatible) for language tasks** — intent extraction, grounded explanations,
critique, judging. Chosen for function-calling support (structured outputs via LangChain),
essentially negligible cost at portfolio scale, and full-fallback design: no key, no LLM, system
still works.

## Alternatives considered

- FashionCLIP / SigLIP: likely better fashion embeddings; deferred until an eval shows the base
  model is the bottleneck (the labeled product fixtures now make that measurable).
- OpenAI/Claude APIs: better models, but the tasks are deliberately simple enough for a budget
  model precisely *because* outputs are schema-validated and rule-checked.
- Fine-tuning: no labeled data that would beat zero-shot + retrieval; revisit if user-correction
  data (wardrobe tag fixes, feedback) accumulates.
