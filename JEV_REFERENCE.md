# JEV (TypeSafe AI) — Engineering Reference

**Audience:** an AI coding agent that needs to understand JEV well enough to design with it and write correct integration code.
**Compiled:** 2026-09-22 · **Model at time of writing:** `jev-1.13.0`
**Standalone document.** No project context assumed.

> **Volatility warning.** Jev launched **15 September 2026**. This reference is one week old relative to the product. Pricing, rate limits, aliases and model behaviour are all explicitly documented as subject to change. Verify against `https://docs.typesafe.ai` before relying on any number here. A machine-readable doc index lives at `https://docs.typesafe.ai/llms.txt` and the full text at `llms-full.txt`.

---

## 1. The one-paragraph version

Jev is a **"System One" model**: it does not generate text, write code, or hold a conversation. You send it a **state** (the material to judge) plus a set of **typed questions**, and it returns **typed answers with calibrated probabilities** that your code branches on directly. No parsing, no "please return JSON," no retry loop when the model returns prose instead. It is priced at **$0.042 per million input tokens with output free**, responds in roughly **100ms**, and evaluates every question in a request **in parallel and in isolation**.

The mental model the docs push: Jev is **a smart `if` statement**. Ordinary code branches fine on computable values and falls apart when the condition is a judgment — "is this message angry," "is this passage relevant," "is this tool call dangerous." Jev makes those conditions computable.

The governing design rule, worth memorising:

> **Questions describe judgments. Code owns composition, thresholds, and side effects.**

---

## 2. What it is not

This is the section most integrations get wrong, so it comes before the API.

| Jev is NOT | Because |
|---|---|
| A replacement for your LLM | It emits no text. There is no config flag that turns a chat model into Jev. |
| A chat model | No conversation, no system prompt, no roles. One state, N questions, one response. |
| A reasoning model | It is explicitly System One — fast intuitive judgment, not deliberation. Decompose System Two work into several System One questions and combine in code. |
| A calculator | See §7.2. It is bad at arithmetic, counting, and date comparison, by design. |
| A text generator or extractor | Chaining choices to force generation is "poor and slow." Bound the answer space instead. |
| Fine-tunable | Identical weights for every account. No LoRA, no training on your data. You customise via `state`, `instructions`, and `criteria` only. |
| Guaranteed correct | Calibration is measured *across groups of predictions*. It says nothing about whether any individual answer is right. A wrong label drawn from your allowed list is still wrong — type safety narrows the *shape* of a failure, not its existence. |

**The canonical architecture is a cascade:** Jev classifies and routes cheaply → deterministic code handles what it can → a frontier LLM takes the hard minority.

---

## 3. The API

### 3.1 Endpoint

```http
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer $TYPESAFE_API_KEY
Content-Type: application/json
```

Also: `GET /v1/models` lists the model names your account may use.

### 3.2 Request

```json
{
  "state":  "...",              // string | object | array  — the material to judge
  "model":  "jev-latest",       // or a pinned version, e.g. "jev-1.13.0"
  "questions": {                // keys are YOUR ids; answers return under the same keys
    "<your_id>": { "type": "noul" | "choice" | "score", "instructions": ..., "criteria": ... }
  }
}
```

Question ids are **not shown to the model** — they are purely for your code. `instructions` and `criteria` values may each be a **string, object, or array** (§5.4).

### 3.3 The three primitives

#### `noul` — yes/no, returns a probability

The name is TypeSafe's coinage for a yes/no question that returns a probability rather than a boolean.

```json
{
  "is_urgent": {
    "type": "noul",
    "instructions": "Does this convey urgency?",
    "criteria": {                                  // optional but usually worth it
      "true":  "Explicitly time-sensitive",
      "false": "No urgency expressed"
    }
  }
}
```
```json
{ "type": "noul", "noul": 0.95 }
```

- Value combines **answer and certainty in one number**. ~1 firm yes, ~0 firm no, ~0.5 genuinely split.
- **No `confidence` field**, and this is principled: with only two outcomes, the single value already describes the entire distribution.
- The 0–1 range is **not a scale of the underlying attribute**. If you want degree, use `score`.
- One condition per noul. "Angry *and* asking for a refund" dilutes the value — split it, combine in code.
- Phrase so that **high means yes**. Inverted wording is a reliable source of downstream bugs.

#### `choice` — pick exactly one of up to 255 options

```json
{
  "department": {
    "type": "choice",
    "instructions": "Which team should handle this?",
    "criteria": {
      "billing":   "Payments, invoicing, refunds",
      "technical": "Bugs, outages, integrations",
      "sales":     "Pricing, upgrades, new accounts",
      "other":     null
    }
  }
}
```
```json
{
  "type": "choice",
  "choice": "billing",
  "probabilities": { "billing": 0.88, "technical": 0.12, "sales": 0.0, "other": 0.0 },
  "confidence": 0.81
}
```

- `criteria` is a map of **option name → description**. `null` descriptions are fine when names are self-explanatory; **both names and descriptions reach the model**, so names carry real signal.
- Up to **255 options**, each costing only a few tokens — supply the full taxonomy, not a trimmed subset.
- **Options must be mutually exclusive.** `probabilities` spans all options and sums to 1, so overlap is meaningless. Overlap shows up as split probability: a multi-issue ticket gave `returns` 0.61 / `billing` 0.35 / confidence 0.42.
- Write descriptions **contrastively** — their job is to separate options from each other, not to describe each in isolation.
- **Always include an `other` / `none of the above` escape** when input may fall outside the list.
- `choice` is just the argmax of `probabilities`. Secondary options above a threshold (~0.25) are a useful signal in their own right — e.g. copy a second team.
- Deep taxonomies: chain one Choice per level and run a **beam search over probabilities**, keeping the top K paths rather than greedily taking the best at each level.

#### `score` — position on an ordered 2–10 level rubric

```json
{
  "frustration": {
    "type": "score",
    "instructions": "How frustrated is the customer?",
    "criteria": ["Calm", "Frustrated", "Very angry"]   // ORDERED ARRAY, low → high
  }
}
```
```json
{
  "type": "score",
  "score": 1.05,
  "legend": { "0": "Calm", "1": "Frustrated", "2": "Very angry" },
  "probabilities": { "0": 0.0, "1": 0.95, "2": 0.05 },
  "confidence": 0.92
}
```

- A level's number **is its array index**. The ordering *is* the numbering. Minimum 2 levels, maximum 10.
- **The score is a probability-weighted mean, not an interpolation.** `0×0.0 + 1×0.57 + 2×0.43 = 1.43`. It ranges 0 → top level number.
- ⚠️ **Different distributions produce the same score.** A 1.0 could be all mass on level 1, or an even split across 0 and 2. Always read `probabilities` and `confidence` alongside it.
- The fractional part carries **no domain meaning** beyond position. A severity of 1.43 does not mean "43% of customers affected." You may rank by it or round to the nearest level; do not do arithmetic on it as though it were a measurement.
- **The model receives only the level descriptions, and judges each independently.** Therefore:
  - Relational phrasing ("worse than the previous level") is meaningless.
  - **Bare numeric criteria perform badly.** Documented: `["0","1","2"]` produced 0.55 @ confidence 0.33, while descriptive levels produced 0.0 @ confidence 1.0 on the same input.
  - Describe **situations, not degrees**. "Moderately severe" gives nothing to match against.
- One dimension per question. A level bundling "punctual and smart and experienced" cannot place an input that is high on one and low on another.
- **Give rare extremes their own level** if you will act on them differently — a scale topping out at "very angry" should add "abusive or threatening."
- Low confidence on a score usually means: overlapping levels, a multi-dimensional question, or a state too thin to place.

### 3.4 Response envelope

```json
{
  "model": "jev-1.13.0",
  "answers": { "<your_id>": { ... } },
  "usage":  { "input_tokens": 512, "output_tokens": 0 }
}
```

### 3.5 Errors

| Code | Meaning | Handling |
|---|---|---|
| 401 | Bad key | Fail fast |
| 422 | Validation failure — body names the offending field | Fix the request; do not retry |
| 429 | Rate limited | Exponential backoff, respect `retry-after`; SDKs do this by default |
| 529 | Overloaded | Exponential backoff |

---

## 4. SDKs

### 4.1 JavaScript / TypeScript

```sh
npm install @typesafe-ai/sdk      # Node.js 20+. Ships ESM, CJS, and .d.ts
```

```ts
import { choice, noul, score, TypeSafeClient } from "@typesafe-ai/sdk";

const client = new TypeSafeClient();          // reads TYPESAFE_API_KEY from env

const response = await client.systemOne({
  state: { document: "I was charged twice. Please fix this ASAP." },
  questions: {
    category: choice("What is this ticket about?", {
      billing: null,
      technical: null,
      other: null,
    }),
  },
});

response.answers.category.choice;         // "billing"
response.answers.category.probabilities;  // { billing: 0.9, ... }
response.answers.category.confidence;     // 0.87
```

Answer types are **derived automatically from the questions you supply**, so `response.answers.<id>` is correctly typed per primitive. Exported error classes: `APIError`, `APIConnectionError`, `APITimeoutError`, `AuthenticationError`, `BadRequestError`, `RateLimitError`, `InternalServerError`, `NotFoundError`, `PermissionDeniedError`, `UnprocessableEntityError`, `APIUserAbortError`.

> Note: the JS SDK docs page only demonstrates the `choice` helper. `score` and `noul` helpers exist in the type reference (`ScoreQuestion`, `NoulQuestion`, and exported functions `choice`, `noul`, `score`), but confirm their exact signatures against `client.ts` / `types.ts` in the package before writing against them from memory.

### 4.2 Python

```sh
pip install typesafe-sdk --index-url https://pypi.typesafe.ai/
```

```python
from typesafe_sdk import Choice, Noul, NoulCriteria, Score, TypeSafeClient

client = TypeSafeClient()                     # reads TYPESAFE_API_KEY
response = client.system_one(state=..., questions={...})
response.answers["category"].choice
```

Sync and async clients both available, with built-in retry policy.

### 4.3 LangChain

```python
from langchain_typesafe import Noul, TypeSafeClassifier

classifier = TypeSafeClassifier()
response = classifier.invoke({
    "state": "The deploy failed twice and customers are seeing 500s.",
    "questions": {"urgent": Noul(instructions="Does this need attention right now?")},
})
response.nouls["urgent"].noul
```

State accepts plain text, structured data, **or LangChain messages** — so it can be called from a node or middleware hook using context the agent already holds.

Experimental agent middleware (`langchain_typesafe.experimental.middleware`) provides `ModelRouterMiddleware` (route between a cheap and an expensive model per turn) and `AutoModeMiddleware` (gate risky tool calls). These sit under `experimental` — APIs are not stable.

### 4.4 Other access routes

- **Playground / keys:** `console.typesafe.ai`
- **Vercel AI Gateway**
- **Agent skill** (gives a coding agent correct API context):
  `claude plugin marketplace add typesafe-ai/skills && claude plugin install typesafe@typesafe-ai`
  or `npx skills add typesafe-ai/skills --skill typesafe-ai`

---

## 5. The `state`

### 5.1 Accepted shapes

| Shape | Use for |
|---|---|
| string | A message, article, or passage |
| object | Named fields, related records, application state — **recommended default** |
| array | A sequence of messages or records |

Objects are preferred for most requests because each piece of state carries a descriptive name the model can be pointed at.

### 5.2 Referencing state inside a question

Use dot-and-index paths **wrapped in backticks** inside `instructions` to remove ambiguity:

```
"Does `support.tickets[0].message` request a refund?"
```

The same mechanism works for values placed inside structured `instructions`.

### 5.3 The separation principle

> **Source material and supporting facts go in `state`. The judgments themselves go in `questions`.**

### 5.4 Structured `instructions` and `criteria`

Both accept string | object | array. Start with plain strings. Escalate to objects when:

- two options keep getting confused with each other,
- part of the question is injected from your code,
- several questions share near-identical wording,
- the model persistently splits probability between neighbouring score levels.

Field names inside those objects (`what`, `not_for`, `examples`, `signals`, `focus`, `question`) are **entirely your invention — none are reserved by the API**. The model reads the field names too, so keep them short and descriptive, and keep them **parallel across options** so they compare cleanly.

Worked evidence on examples: on one bug report, adding a **well-matched** example moved the result from score 1.43 / confidence 0.35 → 1.03 / 0.96. Adding an **unrelated** example changed nothing. Examples only help when they resemble real inputs — and higher confidence is not proof of correctness, so validate against held-out data.

### 5.5 Hard constraints

- **Text only.** No images, audio, or video. Convert to text first.
- **English is primary.** Other languages including CJK are accepted at **reduced accuracy**. Test before deploying non-English traffic.
- **Context rot is real.** Accuracy degrades as state fills with unrelated content. Filter in code first — do not send a customer's entire history to score one ticket.

---

## 6. Confidence

Returned on **`choice` and `score` only**, never on `noul`.

- It is a **statistic computed from the `probabilities` already in the response** — a scalar summarising how *peaked* the distribution is. Mass concentrated on one outcome → high. Mass spread → low.
- Probability and confidence are different axes: probability is per-option and sums to 1; confidence is one number describing the shape of that whole set.
- The docs are explicit that their definition is **a convenience, not a constraint** — "you are never locked into our definition." That is why the full distribution ships in every response. Compute your own if you prefer.
- A flat **choice** distribution usually means no clear winner among the options you gave. A flat **score** distribution usually means ambiguous, multi-dimensional, or underspecified levels.
- **The answer tells you *what*. Confidence tells you *whether you should act unattended*.**

### 6.1 Threshold design

Three bands: **act automatically / proceed with caution (confirm, flag, gather more) / decline to act.**

The critical principle: **thresholds scale with the consequences of being wrong, and one system should gate different actions at different levels.**

```python
if confidence < 0.5:
    route_to_human(user_message)          # genuine uncertainty floor
elif action.choice == "check_balance":
    show_balance(account_id)              # read-only, recoverable → loose gate
elif action.choice == "approve_transfer":
    if confidence > 0.9:
        confirm_then_execute(account_id)  # destructive → strong signal required
    else:
        ask_user_to_confirm(account_id)
```

Threshold values appearing across the docs, as **starting points only**:

| Context | Value |
|---|---|
| Generic uncertainty floor → human | `< 0.5` |
| Generic routing → human review | `< 0.8` |
| Voice banking floor → agent | `< 0.6`; `approve_transfer` 0.6–0.85 confirm, `> 0.85` auto |
| Topic confidence → human review | `< 0.75` |
| Noul treated as true | `>= 0.7` |
| Spam quarantine | `>= 0.6`; 0.4–0.6 → human review |
| Composite gate | confidence `>= 0.7` **and** score `>= 1.5` |
| Guardrails `strict` policy | review `>= 0.35`, block `>= 0.70`, severity block `>= 2.0` |
| Guardrails `permissive` policy | review `>= 0.35`, block `>= 0.85`, severity block `>= 2.0` |

> **Do not copy these.** Correct values are domain- and version-specific. Start conservative, calibrate against labelled examples from your own traffic, and re-calibrate when the model version changes (§8.2).

---

## 7. Patterns

### 7.1 Atomic questions (the foundational one)

Never ask one big question. Decompose into narrow judgments and compose in code.

> Instead of "rate this startup pitch," ask separately about market size, technical feasibility, and differentiation, then apply your own formula.

The payoff: reweighting becomes **editing a coefficient**, not rewriting a prompt. Each judgment is independently inspectable and independently testable.

Heuristic from the docs: *if you catch yourself explaining what you actually meant, that explanation is the missing half of the instruction.*

### 7.2 Speculative fan-out — *cost, speed*

Send **every question your decision tree might need** in one call, including ones that will likely be irrelevant, and discard unused answers in code.

Why this is free: questions are evaluated in parallel and in isolation, so adding questions barely moves latency and introduces no context-rot between them. You only pay the extra question tokens.

Support-triage example: one call sends a `choice` for category, `score`s for bug severity and frustration, and `noul`s for reproducible steps and refund request. `bug_severity` only matters if it is a bug and `refund_requested` only if it is billing — both are sent anyway. One round trip covers the whole decision tree instead of chaining follow-up calls.

Measured: one cookbook reports batching as **12.2× cheaper and 10.0× faster** than sequential calls. Another sent 62 questions in a single request (0.51s).

### 7.3 Intent routing — *cost, speed*

Classify first, then route to **deterministic code / a specialist LLM / a human**. The single highest-value pattern for chat and support systems.

```python
resp = client.system_one(state=message, questions={
    "intent":     Choice(instructions="What does the user want?", criteria={...,"other":None}),
    "complexity": Score(instructions="How difficult is this?",    criteria=[...3 levels...]),
})

i = resp.answers["intent"]
if i.confidence < 0.5:              route_to_human()
elif i.choice == "order_status":    deterministic_lookup()          # no model at all
elif i.choice == "product_question":specialist_llm(ctx=PRODUCT_DOCS)
elif i.choice == "return_exchange": specialist_llm(ctx=RETURN_POLICY)
elif i.choice == "complaint":
    c = resp.answers["complexity"]
    if c.score > 1 or c.confidence < 0.5: route_to_human()
    else:                                 complaint_llm()
```

Note the **double confidence check** on the complaint branch: low confidence means different things depending on what is at stake. Classification is one quick call, so expensive resources are reserved for requests that genuinely need them.

### 7.4 Confidence-gated routing — *reliability, safety*

Covered in §6.1. The essence: **answer and confidence are two independent axes**, and the second one decides whether to act, confirm, or escalate.

### 7.5 Composite scoring — *cost, reliability, speed*

Decompose one complicated judgment into several `score` dimensions in a single call, normalise, and weight **in your code**.

```python
py    = r.answers["python_depth"].score   / 4     # normalise 0–4 → 0–1
lead  = r.answers["leadership"].score     / 4
arch  = r.answers["system_design"].score  / 4
gen   = r.answers["generalist"].score     / 4

ic_score = 0.40*py + 0.10*lead + 0.40*arch + 0.10*gen   # senior IC
em_score = 0.15*py + 0.40*lead + 0.20*arch + 0.25*gen   # eng manager
```

The real benefit is **transparency into the arithmetic behind the final number**. When rankings look wrong you tune a weight instead of re-engineering the judgment. Same questions, different role profiles, no extra API calls.

### 7.6 Two-stage dependency

Make a second call only when the first **changes the state or the option set** — e.g. level 2 of a taxonomy whose options depend on the level 1 answer. Otherwise prefer fan-out (§7.2).

### 7.7 Guardrails for LLMs — *the flagship safety pattern*

Screen the inbound user message and the outbound model reply, each in **one call**, with mirrored batteries: the input side asks whether the user *requested* something; the output side asks whether the reply *delivered* it.

Documented battery shape — **four hazard nouls + one harm score**:

```
noul  jailbreak            # inbound: override attempt.  outbound: reply broke policy
noul  harmful_request      # harm or crime
noul  medical_advice       # diagnosis or dosage
noul  self_harm            # signs of self-harm
score severity             # 0–3 written scale, "no harm" → "Severe"
```

Policy lives in **your** code as a two-threshold-per-hazard table plus a hazard→action map:

```python
POLICIES = {
    "strict":     {"review": 0.35, "action": 0.70, "severity_block": 2.0},
    "permissive": {"review": 0.35, "action": 0.85, "severity_block": 2.0},
}
HAZARD_ACTION = {
    "jailbreak":       "block",
    "harmful_request": "block",
    "medical_advice":  "review",
    "self_harm":       "route_to_support",
}
# severity can escalate a "review" into a "block"
```

**Why four outcomes (pass / review / block / route) instead of a binary blocker** — the published sample run shows exactly what binary misses:

- A mild melatonin dosing question → **review**, not refusal.
- A self-harm message → **routed to support**, not shut down.
- A novelist asking how a fictional poisoning would read → **passes** despite violent content.
- An assistant *declining* to help with a burglary → **passes** on the outbound side.
- A headache-dosage request at `medical_advice` 0.95, severity 2.02 → **the severity score is what tips it from review to block.**

And the same cached assessment (`jailbreak=0.74`) **blocks under `strict` but only flags under `permissive`** — the probabilities are fixed; the product chooses its own evidence bar.

> **The structural reason this beats prompt-based guardrails:** the gate runs *before* the LLM, so a blocked message never enters the model's context at all. A message the model never sees cannot influence it. "The system prompt says don't" is a soft guarantee that degrades under adversarial input; this is a separate, cheap, calibrated decision the user cannot argue with.

### 7.8 RAG passage filtering

Score each retrieved passage for **relevance, answer support, contradiction, and injection risk**; only evidence clearing your thresholds reaches the answering model. Directly mitigates both context rot and prompt injection via retrieved content.

### 7.9 Re-ranking

BM25 or embeddings build the shortlist; each query–candidate pair then gets a `noul`, and you **sort by the raw probability**. This avoids asking a generative model to invent a scale — the probability *is* the scale, and it is calibrated.

### 7.10 Tool-call risk gating

Screen proposed tool calls before execution: deny / ask / allow. The docs note that closed-source coding harnesses have always done this internally; a cheap classifier lets any agent adopt the pattern.

---

## 8. Failure modes — the "jaggedness" list

TypeSafe publishes a per-version page of known rough edges. For **Jev 1.13**, nine documented failure modes. Read this before designing, not after debugging.

### 8.1 Literal reading
> "Jev answers the question you wrote, not the one you meant."

Scoping terms, negations, and implied conditions are taken at face value.
**Fix:** spell out the exact condition in `instructions`; put boundary cases in `criteria`; split ambiguous asks into two literal questions and combine in code.

### 8.2 Math and numbers — *"Jev is not a calculator"*

- **Counting** is unreliable — characters in a word, occurrences of a term, items in a long list. The model "recognizes the shape of an answer rather than tallying," and error grows with size.
  **Fix:** loop in code, one noul per candidate, sum the results yourself.
- **Numeric representations** underperform semantic ones. Colour questions work far better with English names than hex/RGB, and it cannot reliably judge whether two numeric colour values are close. High-level languages beat assembly or binary.
  **Fix:** convert in code, pass a name or a bucket. Reserve the model for the judgment ("does this colour read as a warning?").
- **Do not interpolate a score** to recover an exact number — score levels are weak in numerical calibration. Thresholding the expectation is fine.

### 8.3 Date and time comparison
Dates are read **as text, not as ordered quantities**. Ordering, gaps, and window membership are unreliable — worse with mixed formats, relative references, and boundaries like quarter ends.
**Fix:** model extracts, code computes. Each date component is a small closed set, so use a `choice` over enumerated options **plus an explicit "not stated" option** so missing parts get reported rather than invented.

### 8.4 Indirection
Double negatives and multi-hop reasoning — "a property of a property" — cost accuracy.
**Fix:** write directly, name the relevant state explicitly.

### 8.5 Large state full of irrelevant detail
Unrelated content acts as a distractor and obscures which input caused an error.
**Fix:** retrieve and filter in code first. If you cannot, use a noul as a relevance filter (§7.8).

### 8.6 Adversarial content
> **State is treated as data, not as hostile.**

Injected instructions, misleading framing, or text that argues for its own classification **can shift the answer**. Improvement is expected in later versions.
**Fix:** be explicit in criteria, test adversarially before deployment, and do not make Jev your only line of defence against an attacker who controls the state.

### 8.7 Contradictory instructions and criteria
A noul whose `true` description means "no" performs measurably worse.
**Fix:** treat criteria as an *extension* of the instruction. Aim for phrasing an average reader would understand.

### 8.8 Common-sense structural invariants do not hold

Jev is **extremely consistent across semantically similar inputs**, yet invariants you would assume simply are not true. Two documented examples on the same input ("I'm not happy with the fit. What are my options here?"):

| | Result |
|---|---|
| As a **noul** | `0.22` |
| As a yes/no **choice** | `yes` 0.01 / `no` 0.99 / confidence 0.97 |

And a question with its own negation, as two nouls on a double-charge ticket:

| | |
|---|---|
| `refund` | 0.72 |
| `not_refund` | 0.47 |
| **sum** | **1.19 — not 1** |

**Consequences, both load-bearing:**
1. **Never port a noul-tuned threshold to a choice**, or vice versa.
2. **Never expect arithmetic identities across separate questions.** A choice is *relative* (which option wins); a noul is *absolute* and can legitimately be low for every option.

### 8.9 Generation
Not trained to generate. Chaining choices to force it is poor and slow.
**Fix:** bound the answer space and make extraction a `choice`; or extract candidates with regex or a generative model and let Jev **pick**.

### 8.10 Summary of things to avoid

- Asking for what code can compute exactly
- Bundling multiple judgments into one question
- System Two tasks with layered indirection
- Over-stuffing `state` — **"Jev suffers from context rot"**

---

## 9. Limits, pricing, operations

### 9.1 Models

| Name | Resolves to | Notes |
|---|---|---|
| `jev-1.13.0` | itself | Pinned version |
| `jev-latest` | `jev-1.13.0` | Most recent **stable official** release. SDK/doc default. |
| `jev-preview` | `jev-1.13.0` | Most recent release official or not; currently identical |

All route to the same `POST /v1/systemone`; the `model` field selects.

> **Pin the versioned id once you have calibrated confidence thresholds.** Aliases move when releases ship, and §8.8 shows how version-sensitive calibration is. The response `model` field always reports which version actually answered — log it.

### 9.2 Context and rate limits

| Limit | Value |
|---|---|
| Total per request | **64k tokens** (state + all questions) |
| State + single longest question | **32k tokens** |
| Choice options | 255 max |
| Score levels | 2 min, 10 max |
| Questions per request | Not documented; 62 observed in one cookbook |
| Throughput | 250,000 tokens/sec |
| Requests | 1,200/min |
| Over either | `429`, with `retry-after` where present |

Rate limits are documented as **"adjusting dynamically"** and may shift without notice while demand is high. Higher ceilings on custom/enterprise plans.

### 9.3 Pricing

**$0.042 per million input tokens ($42/Btok). Output tokens are free** — there are none. TypeSafe describes it as "too cheap to meter."

Reference points:
- $5 free credit on signup ≈ **120 million tokens**
- Vendor's internal eval: **$0.0004/case for Jev vs $0.0304 for a frontier model** — ~76×
- Community: an SEO audit ran 4,816 typed judgments for **$0.0048 per 12-query triage batch**

> All comparative multiples ("193× faster, 445× cheaper," "200× faster, 400× cheaper") are **vendor self-reported and unaudited**. Benchmark your own workload.

**Budgeting formula:**
```
cost = (state_tokens + sum(question_tokens)) × requests × $0.042 / 1e6
```
Because questions batch in parallel, adding a question adds only its own tokens — not a new request, and effectively no latency.

### 9.4 Latency

~**70–500ms** end-to-end; docs cite ~**100ms** typical and ~150ms for real-time use. Observed in cookbooks: 16 questions in 0.32s, 62 questions in 0.51s.

**Adding questions barely changes response time.** This is the single most important operational property — it is what makes §7.2 free.

### 9.5 Data handling

- Customer requests and responses are **not used for training**.
- No fine-tuning or LoRA — identical weights for every account, trained with **RLCD** (reinforcement learning for calibrated decisions).

### 9.6 Access

Waitlist **removed 21 September 2026**. Open signup at `console.typesafe.ai` with $5 free credit. Company: TypeSafe AI, San Francisco; out of stealth 15 Sep 2026 with $40M seed led by DCVC; founded by Diogo Almeida, co-inventor of RLHF/InstructGPT at OpenAI. TypeSafe cleared ~140,000 signups in the first 36 hours.

---

## 10. Integration checklist

Design:
- [ ] Is this a **judgment**, not a computation? If code can compute it exactly, use code (§8.2).
- [ ] Is each question **atomic** — one condition, one dimension?
- [ ] Right primitive? Unordered categories → `choice`. Spectrum → `score`. Yes/no → `noul`.
- [ ] Choice options **mutually exclusive**, with an `other` escape?
- [ ] Score levels describe **situations, not degrees**, and are never bare numbers?
- [ ] Nouls phrased so **high = yes**?
- [ ] All questions **batched into one request** (§7.2)?
- [ ] `state` **filtered in code** to what the question needs (§8.5)?

Code:
- [ ] Thresholds live in **your code**, versioned and reviewable — not buried in question text.
- [ ] Thresholds **differ per action**, scaled to the cost of being wrong (§6.1).
- [ ] Reading `probabilities` where the scalar is ambiguous (§3.3 score caveat).
- [ ] Model id **pinned** and the response `model` field **logged**.
- [ ] `429`/`529` retried with backoff; `422` not retried.
- [ ] **Timeout + fallback path** defined. Decide explicitly whether to fail open or closed — for safety gating, fail closed.
- [ ] All probabilities **logged** for calibration and audit.

Before production:
- [ ] Calibrated against a **labelled set from your own traffic**, not vendor examples.
- [ ] **Adversarial inputs tested** — state is not treated as hostile (§8.6).
- [ ] Non-English traffic tested separately if applicable (§5.5).
- [ ] A **deterministic fallback classifier** exists for when Jev is unavailable.
- [ ] Recalibration planned for the next model version (§8.8).

---

## 11. Quick decision guide

```
Need a judgment a knowledgeable person could make in seconds?          → Jev
Need text, code, or explanation generated?                             → LLM
Need an exact computation, count, date comparison, or total?           → code
Need multi-step reasoning over layered indirection?                    → LLM, or decompose into several Jev questions
Need to decide WHICH of the above to use, per request?                 → Jev (intent routing, §7.3)
Need to check what an LLM was asked or what it produced?               → Jev (guardrails, §7.7)
Need to pick the best K from a candidate list?                         → shortlist in code, rank with Jev nouls (§7.9)
```

---

## Sources

**Official docs** — `https://docs.typesafe.ai`
[Introduction](https://docs.typesafe.ai/introduction) · [Jev with coding agents](https://docs.typesafe.ai/introduction/coding-agents) · [Confidence](https://docs.typesafe.ai/concepts/confidence) · [Noul](https://docs.typesafe.ai/primitives/noul) · [Choice](https://docs.typesafe.ai/primitives/choice) · [Score](https://docs.typesafe.ai/primitives/score) · [Patterns index](https://docs.typesafe.ai/patterns) · [Intent routing](https://docs.typesafe.ai/patterns/intent-routing) · [Confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing) · [Speculative fan-out](https://docs.typesafe.ai/patterns/fan-out) · [Composite scoring](https://docs.typesafe.ai/patterns/composite-scoring) · [Models](https://docs.typesafe.ai/models) · [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13) · [LLM guardrails cookbook](https://docs.typesafe.ai/cookbooks/llm_guardrails) · [Classifying RAG passages](https://docs.typesafe.ai/cookbooks/classifying_rag_passages) · [JavaScript SDK](https://docs.typesafe.ai/sdk/javascript) · [llms.txt](https://docs.typesafe.ai/llms.txt) / [llms-full.txt](https://docs.typesafe.ai/llms-full.txt)

**Ecosystem**
[LangChain — Building a harness with Jev](https://www.langchain.com/blog/building-a-harness-with-jev) · [awesome-jev-by-typesafe](https://github.com/Anil-matcha/awesome-jev-by-typesafe) (community-maintained, explicitly unofficial)

**Press / context**
[TypeSafe — Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) · [Tom's Hardware](https://www.tomshardware.com/tech-industry/artificial-intelligence/typesafe-ais-jev-offers-an-alternative-to-llms-that-claims-to-be-193x-faster-and-445x-cheaper-system-one-type-model-is-bespoke-for-probabilistic-decision-making) · [DataCamp](https://www.datacamp.com/blog/system-one-models-jev) · [explainx — GA, no waitlist](https://www.explainx.ai/blog/jev-general-availability-no-waitlist-2026) · [Flavio Copes — deep dive](https://flaviocopes.com/jev/)

---

*Compiled from vendor documentation and secondary sources on 2026-09-22, one week after launch. Performance and cost multiples are vendor-reported and independently unverified. Every threshold in this document is a starting point for calibration, not a recommendation.*
