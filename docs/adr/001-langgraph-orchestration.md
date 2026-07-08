# ADR 001: LangGraph for orchestration — but only once routing became real

**Status**: accepted (July 2026)

## Context

The original pipeline was a hand-rolled `for` loop over four stages. Calling it "multi-agent" was
indefensible: no stage made a decision, no path ever varied, and there was no way to express a
retry cycle. Two options were considered once the system gained genuinely conditional behavior
(intent-dependent shopping, wardrobe only for identified users, verifier-triggered rebuilds):

1. Extend the hand-rolled orchestrator with conditional branches and a loop guard.
2. Adopt LangGraph's `StateGraph`.

## Decision

Adopt LangGraph — *after* the behavior justified it, not before. The tipping point was the
verifier cycle: "go back to recommendation exactly once, with tightened constraints" is a cyclic
edge with state, which a linear loop cannot express without reinventing a graph executor.

Key implementation choices:

- The graph state carries the same mutable `AgentContext` the agents always shared, so every
  existing agent worked unchanged as a node.
- The `Orchestrator` remains as a façade over the compiled graph — the REST/SSE contract and its
  tests survived the migration intact.
- Error semantics are encoded in nodes/edges, not exceptions bubbling through a loop: vision
  fatal, downstream partial, intent/wardrobe never fatal.

## Consequences

- Routing decisions are inspectable (each conditional-edge function is a pure function of state)
  and the topology is drawable directly from code.
- `astream(stream_mode="updates")` gave per-node SSE progress essentially for free.
- Cost: a framework dependency and its learning curve. Accepted deliberately — partly as a
  learning objective, partly because the cycle/checkpoint features have a real roadmap
  (conversation memory, resumable runs).
