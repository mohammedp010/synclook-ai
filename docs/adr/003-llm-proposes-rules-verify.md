# ADR 003: LLM proposes, rules verify

**Status**: accepted (July 2026)

## Context

The first LLM integration rewrote template sentences "for tone only" — cost and latency for
functionally identical output, demonstrating nothing. The opposite extreme (LLM chooses the
outfit) was rejected too: outfit constraints here are hard product policy (shopping-intent
exclusions, outfit structure, style compatibility) where hallucination is a liability and a
deterministic engine already encodes the rules.

## Decision

Give the LLM the *language* problems and the rule engine the *authority*:

| Task | LLM role | Deterministic role |
|---|---|---|
| Free-text request | structured extraction → `StyleIntent` | `normalized()` clamps/dedupes/caps; taxonomy mapping enforced |
| Outfit selection | none | rule tables + knowledge ranking + outfit structure |
| Explanation | words it | may cite **only** `rec.evidence` facts; verifier + LLM-judge check |
| Quality gate | critic (occasion mismatch) | completeness, policy, budget, claim checks always run |

Corollary: the entire pipeline must run without an API key. Intent falls back to a keyword
heuristic, explanations to templates, the critic to deterministic checks only.

## Consequences

- Hallucination cannot put a forbidden garment in an outfit — that path simply doesn't exist.
- Every LLM feature has a measurable contract: intent extraction is validated Pydantic; the
  explanation contract ("cite only evidence") is enforced twice — the deterministic verifier
  catches literal violations, the LLM-judge catches semantic ones. The judge found a real bug
  on its first run (occasion cited but not recorded as evidence; faithfulness 0.5 → 1.0 fixed).
- The rule tables stopped being the product's ceiling and became its safety floor.
