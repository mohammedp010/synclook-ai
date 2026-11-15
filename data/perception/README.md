# The perception eval set — what to collect and how to label it

This is the one Phase 0 task that cannot be automated. Everything downstream
(deterministic colour, the VLM+Jev cascade, the guardrail) is judged against
the numbers these labels produce, so the quality of this set is the ceiling on
how much anyone can trust the improvement.

Budget: **an afternoon.** ~2 hours of collecting, ~1 hour of labeling once the
tool is running. The labeling tool is keyboard-driven and saves after every
image, so it is safe to stop and resume.

---

## 1. Collect the photos

Three folders under `data/perception/images/`:

### `holdout/` — target **120 photos**. This is the set that counts.

These must be **real-world photos, not clean product shots**, because
real-world photos are what the product receives. A pipeline tuned on white-
background catalog imagery looks excellent right up until someone photographs a
shirt on their bed at night.

Deliberately vary these axes — roughly even coverage matters more than volume:

| Axis | Spread to aim for |
|---|---|
| **Photo kind** | ~40 on-body / worn · ~30 flat-lay on a bed or floor · ~30 on a hanger · ~20 mirror selfie |
| **Lighting** | ~40 daylight near a window · ~40 indoor warm bulb at night · ~20 overhead white/fluorescent · ~20 dim |
| **Background** | half clean-ish, half cluttered (open wardrobe, bedsheet, floor) |
| **Category** | ≥25 topwear · ≥20 bottomwear · ≥15 outerwear · ≥15 footwear · ≥10 fullbody · ≥10 ethnic (kurta, saree, lehenga, sherwani) · ≥10 accessories |
| **Colour** | **at least 10 navy and 10 black items**, plus charcoal/grey, and several beige/tan/cream |
| **Multi-garment** | ~20 photos showing a full outfit (2+ garments) — these feed the Phase 3 multi-garment work |

> **Why the colour insistence.** Navy-vs-black and beige-vs-tan-vs-cream are the
> confusions the current pipeline makes most, and they are the ones Phase 1
> claims to fix. If the set has three navy items, the fix cannot be proven
> either way.

Your own wardrobe is the best source — it is free, it is legally unambiguous,
and it is exactly the distribution the product serves. Shoot on your phone,
no styling, no cleanup. Photos that look a bit bad are the point.

### `adversarial/` — target **25 photos**. Feeds the Phase 3 guardrail.

Things that are *not* a garment photo but might get uploaded:

- a screenshot of anything (a chat, a website, a receipt)
- a pet, a plant, a meal, a landscape
- a blank wall, a ceiling, an accidental pocket shot
- a person's face with no garment visible
- a garment photo so dark or blurred it is genuinely unusable
- **a garment with prominent text printed on it** (a slogan tee) — this is the
  injection case: text in the image is data, never instruction

### `weak/` — optional, skip for now.

Auto-labeled from catalog product titles. `data/catalog_seed.json` currently
holds only 5 rows and a real ingest spends paid SerpAPI credits, so this split
stays empty until the catalog is populated. The holdout set carries Phase 0
on its own.

### Naming

Anything. The tool reads whatever is in the folder. `IMG_1234.jpg` is fine.
Supported: `.jpg`, `.jpeg`, `.png`, `.webp`.

---

## 2. Label them

```sh
poetry run python evaluation/label_tool.py --labeler mohd
```

Opens `http://127.0.0.1:8900/` automatically. It jumps to the first unlabeled
image and, after each save, to the next one — so you can just keep going.

**Keys:** `↵` save & next · `←` `→` move without saving · `/` focus the type
search · `n` mark as not-a-garment.

Progress is written to `labels.jsonl` after **every** image. Closing the tab
loses nothing.

### What each field means

**Photo kind** — how the photo was taken. `not_garment` (or `n`) hides
everything else; use it for the whole `adversarial/` split.

**Garments visible** — how many distinct garments are in the frame. A person in
a shirt, jeans and shoes is `3`. This drives the Phase 3 multi-garment work.

**Garment type** — the *main* garment, the one a user uploading this photo would
want styled. With 56 options, type a few letters in the search box rather than
scanning. If two names both fit, pick the more specific one (`bomber` over
`jacket`).

**Primary colour** — the swatches are the actual reference points Phase 1
resolves against, so **match against the swatch, not against the word.** If the
garment looks like the `charcoal` swatch, pick charcoal even if you would
casually call it black. This is the single most valuable judgment in the set.

**Secondary colour** — only for genuinely two-colour garments (a striped shirt,
a colour-blocked jacket). Leave empty otherwise. Click again to clear.

**Occasions** — ⚠️ **the field people get wrong.** Tick **every occasion the
garment could honestly be worn to**, not the one it is best for. A navy blazer
is `business_formal` *and* `business_casual` *and* `smart_casual` *and*
`wedding_guest` *and* `date_night` — all five. A plain white tee is
`everyday_casual`, `travel_commute`, `beach_resort`, and arguably
`loungewear`. Three to six ticks is normal; one tick usually means you picked
the best rather than the possible.

This is multi-label on purpose: the whole Phase 2 design rests on occasion fit
being several independent yes/no judgments rather than one winner. A set
labeled as if it were single-choice would quietly teach the eval the wrong
question.

**Formality** — the single level the garment sits at. Hover a level to see its
description; the descriptions are the same text Phase 2 gives the model, so
labeling against them keeps the two honest.

**Notes** — free text, optional. Worth using when you hesitated: *"could be
charcoal or black"*, *"blazer or overshirt?"*. Those notes are where the
interesting disagreements show up later.

### Consistency beats speed

Label in one or two sittings rather than five. If you change your mind about a
convention halfway through, finish the pass and then re-label the earlier ones —
appending a corrected line for the same image supersedes the old one, no
rewriting needed.

---

## 3. Freeze the baseline

Once the holdout split is labeled:

```sh
poetry run python evaluation/perception.py                 # look at it first
poetry run python evaluation/perception.py --set-baseline  # freeze the before-number
poetry run python evaluation/perception.py --record        # persist to Postgres (optional)
```

`--set-baseline` writes `evaluation/perception_baseline.json`. **That file is
the "before" column of the README's metrics table**, and it must be produced by
the current CLIP pipeline *before* any perception change lands. Afterwards,
`--check` fails the build on regression.

Read the **confusion tables** at the bottom of the report, not just the
headline accuracy. "navy → black ×14" is a finding; "colour accuracy 0.62" is
a number.

---

## 4. A note on reproducibility

`labels.jsonl` is committed. **The photos are not** — they are personal
wardrobe images and this repo is public.

That is a real and deliberate tradeoff: an outside reader can audit the
labels, the taxonomy, the metric definitions and the scoring code, but cannot
re-run the suite and reproduce the numbers without their own image set. The
alternative — publishing a folder of personal photographs — is worse.

§5 closes that gap part of the way, on a second split, without closing it on
this one. `holdout` is still the set that counts and it is still private.

---

## 5. The `public` split — reproducible, but not the set that counts

`data/perception/images/public/` holds 191 photos harvested from Wikimedia
Commons, **and they are committed.** Every file is CC BY, CC BY-SA, CC0 or
public domain, so redistribution is permitted; anyone who clones this repo can
run `--split public` and get the same numbers this repo reports.

Built with `evaluation/harvest_commons.py`. 139 are garments (35 distinct
types, 37 of them multi-garment) and 52 are non-garment, flagged
`is_garment_photo: false` — which is how the Phase 3 guardrail gets scored
without needing anyone's private photos.

### Three things about this split that have to stay attached to its numbers

**1. The labels are model-generated, not human ground truth.** Every entry
reads `labeler: "claude-opus-5 (model-labeled, see README §5)"`. They were
judged by eye from contact sheets, colours against a rendered palette swatch
sheet — nothing was computed from pixels, because resolving colour with
`color_palette.resolve()` would score Phase 1 against its own output. But an
eval labeled by a model and then scoring a pipeline that may share the model's
priors is measuring agreement, not correctness. Treat `public` accuracy as a
*regression tripwire* — it catches a change that breaks something — and never
as evidence the system is right.

**2. It is a different distribution from `holdout`, and the two are never
pooled.** Commons is amateur snapshots, studio product shots and museum
garments on mannequins. `holdout` is a user's phone: bad light, mirrors,
clutter, crops. A gain here does not imply a gain there. That is why
`evaluation/perception.py` writes `perception_baseline_{split}.json` rather
than one shared file — a good score on the easier set cannot quietly stand in
for the one that counts.

**3. Occasion labels are partly downstream of the type judgment.** Deciding a
garment is a sherwani largely decides that `festive_ethnic` and `wedding_guest`
are ticked. So occasion accuracy on this split is correlated with type
accuracy rather than independent of it, and a type regression will show up
twice. Read the confusion tables, not the two headline numbers.

### Attribution

CC BY and CC BY-SA oblige us to name the author and the licence. Each label
carries a `provenance` block with the author, the licence, and the Commons
description page:

```json
"provenance": {
  "page": "https://commons.wikimedia.org/wiki/File:...",
  "license": "CC BY-SA 4.0",
  "author": "Tess Mattew"
}
```

**Any image added to this split must carry that block.** It is a licence
condition, not bookkeeping — and it also means any claim made about an image
can be checked at the source rather than taken on trust.

### What this does not replace

~120 `holdout` photos and ~25 `adversarial` photos from the actual phone of
the actual person this is built for. `public` makes the repo auditable by a
stranger. It does not tell us whether the thing works on a real upload.
