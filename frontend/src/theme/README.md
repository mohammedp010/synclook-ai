# Synclook design system

The source of truth a contributor reads instead of re-deriving conventions from
component code. It is written as the system is built, phase by phase, and never
lags the implementation — a token or pattern that changes changes here in the
same commit.

Form: **Industrial Quote Grammar**, locked in Plan v2 Phase 3. The direction
contract lives in `.impeccable/surfaces/frontend.md` and is the authority above
this document. Nothing here may be copied into JSX, comments, or anything served
to a browser.

> This file lives at `src/theme/README.md`, not at `frontend/DESIGN_SYSTEM.md`.
> That path held v1's rejected monochrome system and was deleted in Phase 5;
> reusing it would put the new system where the anti-reference used to be.

| Layer | Phase | State |
|---|---|---|
| Typography | 6 | **Landed** — below |
| Colour, surface language, spatial system, motion grammar | 7 | **Landed** — below |
| Flow architecture / IA | 8 | **Landed** — [`src/navigation/routes.ts`](../navigation/routes.ts) |
| Component conventions | 9 | **Landed** — below |
| The wait | 10 | Not written |
| Motion, applied | 11 | Not written |

---

## Typography

Source of truth: [`type.ts`](./type.ts). `tailwind.config.js` carries a
hand-copy of `families` and `sizes` because it is plain CommonJS and cannot
import a TypeScript module — **change the two together or NativeWind and
StyleSheet drift apart silently.**

### Faces

| Family token | Face | Weight | Asset |
|---|---|---|---|
| `stencil` | Big Shoulders Display | 900 | `BigShouldersDisplay_900Black` |
| `stencilMid` | Big Shoulders Display | 700 | `BigShouldersDisplay_700Bold` |
| `plate` | Martian Mono | 400 | `MartianMono_400Regular` |
| `plateBold` | Martian Mono | 700 | `MartianMono_700Bold` |
| `text` | Archivo | 400 | `Archivo_400Regular` |
| `textMid` | Archivo | 500 | `Archivo_500Medium` |

All three families are SIL OFL 1.1, which permits app embedding and web serving.
Designers, versions and the full licence record are in the surface brief.

**React Native resolves a weight by family name, not by `fontWeight`.** Every
weight is a separate `expo-font` asset and a separate `fontFamily` string, so
the weight count is a real budget: six assets, ~546 KB. A seventh needs an
argument. Setting `fontWeight` on a `Text` does nothing useful here — pick the
family that already is that weight.

Fonts load once, in `App.tsx`, via `useFonts(fontAssets)`. Nothing renders until
they resolve, so no screen ever paints in a system fallback and then reflows.

### Two ramps

The world has two registers and no middle, so there are two scales rather than
one ladder. Display steps by ~1.385, hard enough that a stencilled word is never
*slightly* larger than the one beneath it. Text steps by ~1.1, dense label
increments that carry the margin density the contract asks for.

```
display   d1 22   d2 30   d3 42   d4 58   d5 80
text      t1 10   t2 11   t3 12   t4 13   t5 15   t6 17
```

Deliberately **not** 4/8/12/16/20/24/32/48 — that ladder is v1's, and a scale
inherited from the rejected build carries the rejected build's rhythm.

**The display ramp stops at 80 for a measured reason.** The vision pass emits a
closed vocabulary (`backend/schemas/clothing.py`); its longest tokens are
`STREETWEAR` and `MINIMALIST`. Measured in the shipped binary, `"STREETWEAR"`
sets 323pt at 58 and 446pt at 80, against 350pt of usable width on a 390pt
phone. 58 is the largest step the real words survive on a phone, 80 is the
desktop counterpart, and a larger step would exist only to be avoided.

### Roles

Screens reach for a role, never a raw size. A screen that needs a size not on
this list is describing a role the world has not named yet — add it to `type.ts`
with its reason.

| Role | Face | Size | Leading | Tracking | Used for |
|---|---|---|---|---|---|
| `stencilPhone` | stencil 900 | 58 | 50 | −0.6 | The five attribute words over the photograph, phone |
| `stencilDesktop` | stencil 900 | 80 | 69 | −0.8 | The same five, beside the photograph, desktop |
| `stampPhone` | stencil 900 | 30 | 26 | −0.3 | The typed intent, phone |
| `stampDesktop` | stencil 900 | 42 | 36 | −0.4 | The typed intent, desktop |
| `zone` | stencil 900 | 30 | 26 | 0 | A destination naming itself |
| `zoneSmall` | stencil 700 | 22 | 19 | 0 | Display at its floor, where 900 closes up |
| `plateTitle` | plate 700 | 12 | 14 | 1.7 | State inside a plate: `YOURS`, `TO BUY`, `HELD` |
| `plateValue` | plate 400 | 12 | 14 | 1.0 | Attribute plus confidence inside a plate |
| `code` | plate 400 | 10 | 12 | 1.0 | Margins: lot, source, ₹ cap, rebuild count, status |
| `figure` | plate 400 | 11 | 13 | 0.7 | A confidence figure standing under a word |
| `action` | plate 700 | 13 | 15 | 2.1 | The primary action plate |
| `body` | text 400 | 15 | 24 | 0 | Running text |
| `bodySmall` | text 400 | 13 | 20 | 0 | Secondary running text |
| `bodyStrong` | text 500 | 15 | 24 | 0 | Emphasis inside running text |

`letterSpacing` in React Native is **absolute points, not ems**, so every role
computes its own from a ratio in `type.ts`. Do not copy an em value from CSS.

The display leading ratio is 0.86: stacked stencil words read as one block, the
way a set of stencils sits on a crate. Single-line display uses `zone` or
`stamp` rather than tightening `stencil`.

### Rules

- **Display is caps in straight quotation marks, and the quotes are
  load-bearing.** They mark the machine's literal words. Set anything invented
  in quotes and the device becomes cosplay — the honest risk the contract names.
- **Mono is for measurement**, not for a technical mood: codes, figures, ₹
  amounts, state words, source names. It is never running text.
- **Upright is for running text only**, capped at `bodyMeasure` (510pt ≈ 68ch)
  at either frame.
- **State is a word, never colour alone** — `ON` / `OFF` / `HELD` / `FLAGGED`.
- No eyebrow or kicker above a heading, at any size. No tracked-out ALL-CAPS
  label in the upright face; caps belong to the stencil and the mono, which are
  drawn for it.

### Contrast floor

Measured on rendered screens, not on swatches.

| | Cotton (light) | Nylon (dark) |
|---|---|---|
| Ink at full strength | 19.8:1 | 17.4:1 |
| Ink at 0.55 opacity | **4.42:1 — fails AA** | 6.03:1 |
| Ink at 0.6 opacity | 5.25:1 | 6.9:1 |
| Ink at 0.7 opacity | 7.57:1 | 8.97:1 |

**De-emphasis floors at 0.7 opacity.** Cotton is the binding material; nothing
in either theme dims below it.

Safety orange `#FF5A00` measures 6.33:1 as a field under near-black ink and
5.56:1 as ink on nylon, but **3.13:1 as ink on cotton**. On the cotton theme
orange is a field a tag is printed on, never the ink small type is set in.

### Specimen (retired)

Phase 6 proved the scale with a `Specimen.tsx` mounted in `App.tsx`. Phase 9
deleted both, as Phases 6 and 7 said it would when the screens landed. The
evidence is kept: `.impeccable/review/phase6-type/`. The scale is now read off
the screens themselves — `.impeccable/review/phase9-screens/`.

---

## Material

Source of truth: [`material.ts`](./material.ts). `tailwind.config.js` carries a
hand-copy of `colors`, `spacing` and `borderWidth` for the same CommonJS reason
as the type tokens — **change the two together.**

### Colour strategy: Committed

One saturated hue, spent at field scale rather than scattered as accents. Safety
orange owns whole regions — the primary action is a full-width orange plate,
every to-buy piece carries an orange tag — and it never decorates.

Not **Drenched**, because the largest colour event on every screen is the
shopper's own photograph, which is the one thing on screen the app did not make;
a drenched ground competes with the garment the product exists to read. Not
**Restrained** either, which is the trap: v1 was a twelve-stop neutral ramp with
hairline cards and no hue at all, and the verdict was that only the colour theme
had changed.

**There is no semantic colour system.** No success green, no warning amber, no
error red. State is a word — `ON` / `OFF` / `HELD` / `FLAGGED` — and a verifier
failure is struck with hazard tape, which is a pattern rather than a hue. That
is what carries the no-key, no-catalog and partial-result states to a screen
reader without a second mechanism.

### The two materials

A pair, not an inversion. Cotton is a printed ground and nylon a dyed one, and
their planes separate by different amounts because the materials do: cotton
steps 25 tonal points between planes, nylon 16, because a dyed synthetic
separates by sheen and a wide tonal step on a dark ground reads as a raised
card.

| Token | Cotton (light) | Nylon (dark) | Use |
|---|---|---|---|
| `ground` | `#FFFFFF` | `#1A1A1A` | The page. No tint, no gradient, ever |
| `label` | `#E6E6E6` | `#2A2A2A` | A plate's fill |
| `well` | `#D2D2D2` | `#101010` | Sunken — input, letterbox, pressed |
| `ink` | `#0A0A0A` | `#FFFFFF` | Printing ink at full strength |
| `inkDim` | `#4C4C4C` | `#BABABA` | `ink` at 0.7, pre-composited on `ground` |
| `stroke` | `#4C4C4C` | `#BABABA` | A plate's hairline |
| `strokeHeavy` | `#0A0A0A` | `#FFFFFF` | Load-bearing: active zone, read garment, struck plate |

**Cotton opens the app.** Settled from the physical scene in `PRODUCT.md`, not
from preference: the shopper is at an open wardrobe, in a shop under overhead
fluorescents, or by a window in daylight, where a near-black screen is a mirror.
The THESIS also refuses the near-black home by name, and it is what v1
defaulted to. Cotton is additionally the binding material for contrast — every
floor in this system was measured against it, so the theme that opens is the one
that had to clear the higher bar.

Read the active material from `useTheme().material`, never by importing `cotton`
or `nylon` directly. A screen written against one material is a screen that only
works in one theme.

### Tag — the single system hue

`#FF5A00`, and a **field** before it is anything else. It belongs to things that
are *tagged*: the to-buy tag, the ₹ figure hanging off it, the primary action
plate. It never tints a ground, never gradients, never marks emphasis in running
text, and **never appears on a piece the shopper already owns** — owned is
signalled by the absence of a tag plus the word `YOURS`, which is what makes the
orange mean anything.

Near-black `#0A0A0A` prints on the field in **both** materials. Measured: orange
is 6.33:1 as a field under near-black, 5.56:1 as ink on nylon, and only 3.13:1
as ink on cotton. Rather than one rule per theme, the rule is
material-invariant — orange is a surface that near-black prints on — which is
correct for a physical tag and removes the cotton failure by construction.
`tag.inkOnNylon` is the one sanctioned use of orange as ink and only ever on the
nylon ground.

### Hazard — a pattern, not a hue

Black `#0A0A0A` on white `#FFFFFF` diagonals at 45°, 9pt stripes, 16pt band.
**Reserved for one thing: a claim the `VerifierAgent` flagged.** Material-
invariant, because hazard tape is a physical tape — the same tape whichever
garment it is stuck to — and a band of black-and-white on the nylon ground is
genuinely alarming, which is the point. It survives greyscale and colour
blindness, which is why it and not a red carries the flag.

Spending it on anything other than a real verifier failure is the honest risk
the direction contract names, and the fastest way to turn this world into
costume.

### De-emphasis

**0.7 opacity, and there is no second tier.** Cotton binds: ink at 0.55 reads
4.42:1 and fails AA for small text, at 0.6 it is 5.25:1, at 0.7 it is 7.57:1
(8.97:1 on nylon). A third level of grey text is a hierarchy made out of fade
instead of out of type, which is the scale's job.

### Space — additive, not doubling

```
s1 5   s2 10   s3 15   s4 25   s5 40   s6 65   s7 105   s8 170
```

**Each step is the sum of the two before it**, the way lengths of tape are laid
end to end rather than halved. That one rule produces the two registers the type
already has: dense increments at the bottom, where the margins carry real lot,
confidence, ₹ and source codes, and hard jumps at the top, where a stencilled
zone gets a whole region and two zones are never *slightly* apart.

The module is 5 — the stencil pitch, the smallest offset at which a 1pt hairline
and a 3pt corner screw read as placed rather than touching.

Explicitly **not** 4/8/16/24/32/48/64. That ladder is v1's, it is the default
ladder of software in general rather than of anything in this world, and no
value above appears in it.

**Grid.** Cells are square, gutter `s3`, count is the frame's — 2 up on phone, 4
up on desktop — so cell size is a consequence of the frame rather than a fixed
number that wraps a hundred points narrower than its comp. Page margin `s4` on
phone, `s6` on desktop. The desktop left rail is `s8 + s6` = 235, sized from its
contents: `"WARDROBE"` at the 30pt stencil sets ~100pt and the longest
`SYSTEM STATUS` code line sets ~91pt in mono at 10/1.0. Frame boundary 900.

**The rail's material is the counter of the main plane's** — cotton rail against
a nylon plane in the dark theme, nylon rail against a cotton plane in the light
one. Settled in Phase 8, where the direction contract's "fixed left rail,
cotton-white" was literally true in only one theme. The rail is apparatus and
the plane is the work; countering them keeps the pair legible in both materials
instead of making the rail correct in one. Not encoded here — the rail is a
composition, so Phase 9's navigator picks the counter material rather than
`material.ts` exporting a `rail` token that would fix it to one.

### Surface — a plate, not a card

A plane is a **plate**: a square-cornered block of the material one step up,
bounded by a hairline, with four corner screws. The screws are the tell — they
say the block was fastened to the ground rather than floating above it.

| Token | Value | Note |
|---|---|---|
| `radius` | `0` | A rule, not a scale. Every corner is square: a plate is cut, not moulded |
| `hairline` | `1` | Not `StyleSheet.hairlineWidth` — 0.5pt on a 3x screen is a grey suggestion, and this world prints |
| `rule` | `2` | A load-bearing line: a zone rule, the read garment's frame |
| `screw` / `screwInset` | `3` / `3` | One per corner, inset by its own width |
| `platePadY` / `platePadX` | `9` / `13` | Tight — a printed label has no generous interior |
| `actionPadY` / `actionPadX` | `15` / `22` | The one wide plate in the world |
| `misregistration` | `5` | See below |

**Depth is misregistration, not shadow.** There is no elevation scale and no
`shadowColor` anywhere in this system. Two things overlap by being printed out
of register: the second impression sits one pitch down and right of the first,
both fully opaque, both dated. That is what a `VerifierAgent` rebuild looks
like.

**A plate the machine could not fill is struck, never dropped:** `<Plate struck>`
lays one 45° rule across it and clips it to the plate. Fixed at 45°, because
that is the world's one angle — the hazard band's and the cut's. It was drawn
corner to corner, which is 45° only on a square; on a 638×46 plate that came
out at 4°, a near-horizontal rule through the middle of a sentence that read as
a rendering fault. A square still fills corner to corner; a wide plate gets a
short steep cancel mark through its centre. `Plate` fastens its own screws —
never add a second `<Screws>` inside one.

If a future component reaches for a hairline border plus a 14px radius on a flat
ground, that is v1's answer and the SaaS card kit decoloured. Nothing is named
`Card`.

### Motion — a plate is either printed or it is not

| Token | Value | Note |
|---|---|---|
| `cut` | `110` | The 45° wipe. The only animated transition in the world |
| `print` | `0` | A plate arriving. Zero, and meant to be zero |
| `floor` | `90` | Minimum separation between two prints, so two SSE events in one frame still read as two |
| `angle` | `45` | Shared with `hazard.angle` — the strike and the wipe are one gesture |
| `easing` | `linear` | A blade does not accelerate |

**This world has no easing curves, and that absence is the token.** Nothing
tweens a value: no fade, no rise, no spring, no scale-in. What moves is a blade
that wipes a plate into or out of existence at constant speed. `floor` is a
floor, never a schedule — the five words are paced by the real stream, and a
fast response prints all five at once rather than faking a delay.

This deliberately overrides the craft floor's default of an exponential ease-out.
The floor yields to a committed world, and an ease-out here would be the single
most legible way to make the build look like every other app again. The floor's
actual requirement — content visible by default, motion as enhancement — is met
more strictly than by easing: with `useReducedMotion()` true, `cut` is 0 and
every plate is simply printed.

Phase 11 orchestrates one authored moment per screen out of exactly this
vocabulary. No shared entrance-stagger wrapper, ever.

### Dye — content colour, quarantined

`Color` in `backend/schemas/clothing.py` is a closed set of 18 values the vision
pass emits about the user's actual garment. Showing that colour is functionally
necessary — it is product truth, not decoration — so it lives in `dye` and
**nothing in the interface takes its colour from that map.**

**The orange collision, resolved.** `Color.ORANGE` is in the vocabulary, and an
orange garment drawn in `tag.field` would read as a to-buy tag. The dye orange
is a dye orange (`#D2601A`, visibly duller and browner) — and, more importantly,
**a chip is never colour alone**: every chip carries the material's hairline and
its name set beneath it in mono, the same rule the world already applies to
state. That is what lets `white` sit on the cotton ground and `black` on nylon,
and why no contrast floor applies to the swatches themselves.

`other` is `null` on purpose: the pipeline is saying it could not name the
colour, so the chip prints struck rather than guessing a grey.

### Specimen (retired)

Phase 7's specimen proved the material system — both grounds, the tag, the
hazard tape, the additive scale, the plate anatomy, the 45° cut, the dye map —
at both frames in both materials. Captures in
`.impeccable/review/phase7-material/`. The file was deleted in Phase 9 on
schedule; its local `Plate`, `Hazard` and `CutIn` were **not** promoted. The
shipped primitives in `src/components/` were written against the screens that
needed them, which is the point: a primitive that leaks out of a specimen
becomes the default nobody argued for.

---

## Flow architecture

Source of truth: [`src/navigation/routes.ts`](../navigation/routes.ts), mounted
by `src/navigation/RootNavigator.tsx`.

Three routes where v1 had six plus a bottom tab bar:

| Route | Path | What it is |
|---|---|---|
| `Read` | `/read` | The working surface. Initial route. |
| `Wardrobe` | `/wardrobe` | `"THE WARDROBE"` — a layer over the read |
| `PreviousReads` | `/previous-reads` | `"PREVIOUS READS"` — a layer over the read |

**There is no Landing route.** v1's marketing page (nav → hero → "How it works"
→ bento grid → repeated CTA → footer) had no job inside a tool whose entire
proposition is visible the moment the surface opens. Its job is done by the
read surface's cold open, which renders a fully worked synthetic read beside
the empty action, tagged `"SYNTHETIC"`.

**The read surface has phases, not routes.** `ReadPhase = "empty" | "held" |
"reading" | "read" | "struck"`, derived by `readPhase(status, hasImage)`. v1
pushed a new screen for each of these; one surface whose state is printed on it
is the whole point of the form.

**Layers are opaque stack screens that draw their own `Rail`,** not
`transparentModal` cards. The requirement is that the apparatus stays standing
across the boundary; satisfying it by composition rather than by a modal
presentation mode keeps it off `react-native-screens`' web backend.

`AnalysisScope` (`src/navigation/AnalysisScope.tsx`) puts **one** `useAnalysis()`
instance above the navigator. Two instances would let the rail report
`"NO RUN YET"` beside a visibly finished read — a status plate that lies — and
would drop a finished read the moment a layer opened. `useAnalysis` itself is
untouched product truth.

### Frames

Source of truth: [`useFrame.ts`](./useFrame.ts).

| Frame | From | Margin | Grid | Rail |
|---|---|---|---|---|
| phone | 0 | 25 | 2 up | none |
| tablet | 600 | 65 | 3 up | none |
| desktop | 900 | 65 | 4 up | 235 fixed |

Desktop and phone are separate compositions, not one scaled. Desktop splits the
plane; the phone runs one sequence with the primary action pinned to the foot.

**Never compose a grid from `useWindowDimensions()`.** On the web it includes
the scrollbar the page is about to grow, so a two-up grid overflows its
container by ~15pt and every cell wraps to one-up. Measure the container:
`useMeasuredWidth()` returns `[width | null, onLayout]` and returns `null`
until the first layout pass so the caller can hold a frame rather than paint
wrong and reflow.

---

## Components

Source of truth: [`src/components/`](../components/). Flat, thirteen files, no
`ui/` folder and nothing named `Card`. Every name is from the form's world, not
from a component-library vocabulary.

| File | Exports | What it is |
|---|---|---|
| `Plate.tsx` | `Plate`, `Screws`, `impression` | The one container. Square corners, hairline stroke, four corner screws. |
| `Hazard.tsx` | `Hazard` | 45° diagonal band. **Verifier flags only.** |
| `Stencil.tsx` | `WordStack`, `WordRow` | The five attribute words, stencilled caps in straight quotes, confidence in the margin. |
| `ZipTie.tsx` | `ZipTie` | The orange tag that hangs off a to-buy piece: ₹, source, title, retrieval evidence. |
| `Zone.tsx` | `Zone` | A zone naming itself and its state. Replaces a platform title bar. |
| `Margin.tsx` | `Code`, `CodeBlock`, `Rule` | Mono margin data on the 5pt pitch, and the two rule weights. |
| `IntentField.tsx` | `IntentField` | The typed request, set in the stamp role. |
| `GarmentPort.tsx` | `GarmentPort` | The photograph, or the word for its absence. |
| `PiecePlate.tsx` | `PiecePlate`, `OpenSlot` | One piece of the outfit; a slot nothing covered. |
| `ActionPlate.tsx` | `ActionPlate`, `SecondaryPlate`, `MaterialSwitch` | The three action shapes. |
| `StateSwitch.tsx` | `WordSwitch`, `WordSelect` | Binary and n-way state, as words. |
| `SystemStatusPlate.tsx` | `SystemStatusPlate` | The seven pipeline stages, each state a word. |
| `Rail.tsx` | `Rail` | The desktop apparatus: mark, object, zones, material, status. |

### Conventions

- **One container.** There is no card, no panel, no tile, no surface elevation.
  `Plate` with `heavy` for the active one and `struck` for a reduced one.
  `bare` drops the padding when the caller owns it.
- **The mark goes at the head of a square plate and the identity at its foot**
  (`justifyContent: "space-between"`). Stacked from the top, a four-line piece
  leaves the bottom half of a 226pt plate empty and a row of them reads as a
  grid of holes.
- **State is a word in straight quotes**, never a colour, never an icon:
  `"ON"` / `"OFF"` / `"HELD"` / `"YOURS"` / `"TO BUY"` / `"OPEN"` / `"FILED"`.
- **A colour chip is never colour alone** — a 13pt hairline square plus the
  colour's name in mono. `dye.other` is `null`, so an unnamed colour prints
  struck rather than guessed.
- **A genuinely empty slot prints `"NONE"`,** not a dash. At display size in
  Big Shoulders, `"—"` inside straight quotes reads as an underscore. The dash
  is reserved for *waiting*, where nothing is known yet.
- **The material switch names its state off `themeName`, never off the
  material it happens to be printed in.** The rail prints in the counter
  material; reading `m.name` made the rail's switch and the plane's switch give
  two different words for one state.
- **Lot numbers live on the foot code line, not beside the mark.** In a 157pt
  phone cell the mark and the lot collide with no space between them.
- **No arrow suffix, no icon-only control, no badge pill.** A control says what
  it does in the mono action role.
- **44pt minimum on every pressable**, declared as `minHeight` rather than
  inferred from padding.

### The rail (desktop)

235pt fixed, printed in the **counter material** — cotton's rail is nylon and
nylon's is cotton. The apparatus is a different object from the work, and the
form says so with material rather than with a tint. It carries the mark, the
object under the machine (a lot plate), the three zones with live state, the
material switch, and `"SYSTEM STATUS"`.

`SystemStatusPlate` has a `stacked` mode (name line, value line) used in the
rail: two columns need ~165pt and the rail has 159, so the unstacked form broke
`RECOMMENDATION` mid-word. Where it *is* unstacked — the phone's foot plate —
the name column is **115pt**, measured in the browser: `RECOMMENDATION` sets at
112pt in Martian Mono 10/12 at 1pt tracking, and at the first guess of 104 it
broke as `RECOMMENDATIO` / `N`.

**The rail reports the real read, never the fixture.** Its object and lot lines
read `result`, not the synthetic stand-in, and say `HELD, NOT READ` / `—` until
a real read exists. Sourced from the stand-in they printed `T-SHIRT` /
`MOCK-123` over the shopper's own unsent photograph — the fixture's identity
presented as theirs, in the one plate on screen that carries no `"SYNTHETIC"`
tag.

### Composition

- **Desktop read:** rail | read pane (40% of content) | outfit pane. The read
  pane holds the act; the outfit pane holds what the machine returned.
- **Desktop layers:** rail | act column (32% of content) | content pane. The
  act column carries the actions *and* the zone's rules, which is what keeps it
  a column rather than a stub. Ranged full-bleed, a layer was a 1075pt action
  plate with centred type over two-thirds of empty plane.
- **Phone:** one sequence, head strip (mark + material switch) at the top, the
  primary action plate pinned to the foot above the safe-area inset.
- **The desktop stencil steps to d5 (80) only while the read owns the whole
  plane, and back to d4 (58) once the plane splits.** A deviation from Phase 6's
  flat "desktop stencil is 80", made on screen: at 80 in a 424pt pane the five
  words pushed the outfit below the fold.

### Dev overrides

Web-only, `__DEV__`-only, compiled out of a release build. They exist so a
reduced state can be *looked at* rather than reasoned about.

| Query | Surface | Effect |
|---|---|---|
| `?phase=held\|reading\|read\|struck` | `/read` | Forces a read phase |
| `?closet=out` | `/wardrobe` | Forces the service-unreachable branch |

Two limits, both deliberate:

- **An override cannot put a photograph in the store.** Under `?phase=` the
  garment port reads `"NO GARMENT HELD"` even in phases a real run is always
  holding one, and `SYSTEM STATUS` reads `"NO RUN"` because nothing ran. Use a
  real run for any frame where the photograph is the subject; the override is
  for inventorying the plates of a state you cannot otherwise reach.
- **The stand-in is `read`-only.** `?phase=struck` used to hand the synthetic
  read to the outfit pane, which composed a built outfit beside a plate saying
  the garment could not be read — a frame the shipped code never produces. An
  override may compose a state; it may not compose an impossible one.

### Synthetic content

`src/content/synthetic.ts` holds the demonstration read and closet, derived
from `src/api/__mocks__/mockAnalysis.ts`. **Anywhere a reader could mistake it
for their own data it is tagged `"SYNTHETIC"`** — in its zone head, in the rail's
object ID, and on every plate. No commercial claim is ever fabricated: no user
counts, no testimonials, no retailer logos, no uptime.
