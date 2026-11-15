/** Material system — Plan v2 Phase 7.
 *
 *  Derived from the locked direction contract (`.impeccable/surfaces/frontend.md`,
 *  form `Industrial Quote Grammar`), never from a ladder. Every export below
 *  traces to a line of that contract; where it does not, the comment says which
 *  measurement or which schema decided it instead.
 *
 *  COLOUR STRATEGY: COMMITTED.
 *    One saturated hue, spent at field scale rather than scattered as accents.
 *    Safety orange owns whole regions — the primary action is a full-width
 *    orange plate, every to-buy piece carries an orange tag — and it is never
 *    used for decoration, emphasis, or a chart. The two material grounds are
 *    the themes themselves, not a light/dark inversion of one palette.
 *
 *    Not Drenched, and the reason is the subject: the largest colour event on
 *    every screen is the shopper's own photograph, which is the one thing on
 *    screen the app did not make. A drenched ground competes with the garment
 *    the whole product exists to read. The contract already says as much when
 *    it hangs a tag off anything the app did not make.
 *
 *    Not Restrained either, which is the trap: v1 was a twelve-stop neutral
 *    ramp with hairline cards and no hue at all, and the client's verdict was
 *    that it had only changed colour theme. Orange here is a field a tag is
 *    printed on, at page scale, in both themes.
 *
 *  NO SEMANTIC COLOUR SYSTEM. There is no success green, no warning amber, no
 *  error red. The contract settles it: state is a word — "ON", "OFF", "HELD",
 *  "FLAGGED" — and a verifier failure is struck with hazard tape, which is a
 *  pattern rather than a hue. Nothing in this world is signalled by colour
 *  alone, which is also what carries the no-key / no-catalog / partial-result
 *  states through to a screen reader without a second mechanism.
 */

/** The two materials. A pair, not an inversion: cotton is a printed ground and
 *  nylon is a dyed one, and their planes separate by different amounts because
 *  the materials do.
 *
 *  `#FFFFFF` and `#0A0A0A` are named verbatim in the OWN-WORLD block and are
 *  kept for that reason. They also appear in v1's deleted twelve-stop ramp as
 *  its two endpoints, which is a coincidence of both files containing white and
 *  near-black, not an inheritance: v1's light *page* was `#F7F7F6` and its
 *  surfaces were a ramp, where this is one printed material at full strength.
 *  Every other value here is new. */
export interface Material {
  /** Human name, printed in the margins — the material is wayfinding too. */
  name: string;
  /** The page. Full-strength material, no tint, no gradient, ever. */
  ground: string;
  /** A plate's fill: one step of the material, not a raised card. */
  label: string;
  /** Sunken — the intent field the shopper types into, a photograph's
   *  letterbox, a pressed plate. */
  well: string;
  /** Printing ink at full strength. */
  ink: string;
  /** The same ink at `dim`, pre-composited against `ground` so a screen can use
   *  it as a solid where opacity would stack (overlapping strokes, a plate on a
   *  plate). Prefer `ink` + `dim` opacity on text. */
  inkDim: string;
  /** A plate's hairline. Ink at `dim`, which measures 6.9:1 or better against
   *  every plane in its own material — far past the 3:1 a non-text boundary
   *  needs, because a hairline that reads as grey is v1's hairline. */
  stroke: string;
  /** The stroke of something load-bearing: the read garment's frame, the
   *  active zone, a struck plate. Full-strength ink. */
  strokeHeavy: string;
}

/** WHITE COTTON — the light material, and the app's default. Settled from the
 *  physical scene in PRODUCT.md rather than from preference or category habit:
 *  the shopper is standing at an open wardrobe or in a shop under overhead
 *  fluorescents, or by a window in daylight, where a near-black screen is a
 *  mirror. The THESIS also refuses the near-black home outright — it is the
 *  arrangement this category always ships, and it is what v1 defaulted to.
 *
 *  Cotton is additionally the binding material for contrast: every floor in
 *  this file was measured against it because it is the harder of the two, so
 *  the theme that opens the app is the one that had to clear the higher bar. */
export const cotton: Material = {
  name: "WHITE COTTON",
  ground: "#FFFFFF",
  label: "#E6E6E6",
  well: "#D2D2D2",
  ink: "#0A0A0A",
  inkDim: "#4C4C4C",
  stroke: "#4C4C4C",
  strokeHeavy: "#0A0A0A",
};

/** BLACK NYLON — the dark material. Its planes sit closer together than
 *  cotton's (`#101010` / `#1A1A1A` / `#2A2A2A`, 16 points apart) because a
 *  dyed synthetic separates by sheen, not by tone, and a wide tonal step on a
 *  dark ground reads as a raised card. Separation here is carried by the
 *  plate's stroke and its screws. */
export const nylon: Material = {
  name: "BLACK NYLON",
  ground: "#1A1A1A",
  label: "#2A2A2A",
  well: "#101010",
  ink: "#FFFFFF",
  inkDim: "#BABABA",
  stroke: "#BABABA",
  strokeHeavy: "#FFFFFF",
};

export type MaterialName = "cotton" | "nylon";

export const materials: Record<MaterialName, Material> = { cotton, nylon };

/** The theme switch's two positions map onto the two materials. `ThemeName`
 *  stays `"light" | "dark"` because that is what NativeWind's `setColorScheme`
 *  and the persisted preference key already speak. */
export const materialForTheme = { light: cotton, dark: nylon } as const;

/** De-emphasis floor, measured on rendered screens in Phase 6 and unchanged
 *  here. Cotton binds: ink at 0.55 reads 4.42:1 and fails AA for small text, at
 *  0.6 it is 5.25:1, at 0.7 it is 7.57:1 (8.97:1 on nylon). Nothing in either
 *  material dims below this, and there is no second, dimmer tier — a third
 *  level of grey text is how a hierarchy gets made out of fade instead of out
 *  of type, which is the scale's job. */
export const dim = 0.7;

/** SAFETY ORANGE — the single system hue, and a field before it is anything
 *  else.
 *
 *  It belongs to things that are *tagged*: the to-buy tag, the ₹ figure hanging
 *  off it, the primary action plate. It never tints a ground, never carries a
 *  gradient, never marks emphasis in running text, and never appears on a piece
 *  the shopper already owns — owned is signalled by the absence of a tag and by
 *  the word "YOURS", which is what makes the orange mean something.
 *
 *  `ink` is near-black in BOTH materials, deliberately. Measured: orange is
 *  6.33:1 as a field under near-black ink, 5.56:1 as ink on nylon, but only
 *  3.13:1 as ink on cotton. Rather than ship one rule per theme, the rule is
 *  material-invariant — orange is a surface that near-black prints on. That
 *  keeps a tag identical in both themes, which is correct for a physical tag,
 *  and removes the cotton failure case by construction. */
export const tag = {
  field: "#FF5A00",
  /** What prints on the field, in either material. 6.33:1. */
  ink: "#0A0A0A",
  /** The only sanctioned use of orange as ink, and only on nylon (5.56:1).
   *  A screen reaching for this on cotton is a bug — use the field. */
  inkOnNylon: "#FF5A00",
} as const;

/** HAZARD — black-on-white diagonals, reserved for one thing: a claim the
 *  `VerifierAgent` flagged. It is a pattern, not a colour, which is why it
 *  survives a screenshot in greyscale and a colour-blind reader equally.
 *
 *  Material-invariant on purpose. Hazard tape is a physical tape; it is the
 *  same tape whichever garment it is stuck to, and on the nylon ground a band
 *  of black-and-white is genuinely alarming, which is the point. Spending it
 *  anywhere other than a real verifier failure is the HONEST RISK the contract
 *  names, and it is the fastest way to turn this world into costume. */
export const hazard = {
  a: "#0A0A0A",
  b: "#FFFFFF",
  /** Degrees. The same 45 the motion grammar cuts along — a strike and a wipe
   *  are the same gesture at different scales. */
  angle: 45,
  /** One stripe, and the gap equals it. */
  stripe: 9,
  /** Band height where hazard runs under a flagged row. */
  band: 16,
} as const;

/** SPATIAL SYSTEM — additive, not doubling.
 *
 *  Each step is the sum of the two before it, the way lengths of tape are laid
 *  end to end rather than halved. That single rule produces the two registers
 *  this world already has in its type: dense increments at the bottom, where
 *  the margins carry real lot, confidence, ₹ and source codes, and hard jumps
 *  at the top, where a stencilled zone gets a whole region and two zones are
 *  never *slightly* apart.
 *
 *  The module is 5 — the stencil pitch, the smallest offset at which a 1pt
 *  hairline and a 3pt corner screw read as placed rather than touching.
 *
 *  Explicitly not 4/8/16/24/32/48/64. That ladder is v1's, it is the default
 *  ladder of software in general rather than of anything in this world, and a
 *  rhythm inherited from the rejected build carries the rejected build's
 *  rhythm. No value below appears in it. */
export const space = {
  s1: 5,
  s2: 10,
  s3: 15,
  s4: 25,
  s5: 40,
  s6: 65,
  s7: 105,
  s8: 170,
} as const;

/** SURFACE LANGUAGE — what tells two planes apart in this world.
 *
 *  Not a hairline border plus a 14px radius on a flat ground. That was v1's
 *  answer, it is the SaaS card kit decoloured, and the plan names it. Here a
 *  plane is a *plate*: a square-cornered block of the material one step up,
 *  bounded by a hairline, with four corner screws. The screws are the tell —
 *  they say the block was fastened to the ground rather than floating above it,
 *  which is also why there is no shadow anywhere in this file. */
export const surface = {
  /** A rule, not a scale. Every corner in this world is square: a plate is cut,
   *  not moulded. The one exception is a circular screw head, which is drawn,
   *  not radiused. */
  radius: 0,
  /** A plate's bounding stroke. 1, not `StyleSheet.hairlineWidth` — a 0.5pt
   *  line on a 3x screen is a grey suggestion, and this world prints. */
  hairline: 1,
  /** A load-bearing line: a zone rule, the read garment's frame. */
  rule: 2,
  /** The corner screw, one per corner, inset by its own width. */
  screw: 3,
  screwInset: 3,
  /** Plate padding. Tight — a printed label has no generous interior. */
  platePadY: 9,
  platePadX: 13,
  /** The primary action plate, which is the one wide plate in the world. */
  actionPadY: 15,
  actionPadX: 22,
  /** DEPTH IS MISREGISTRATION, NOT SHADOW.
   *
   *  There is no elevation scale and no `shadowColor` anywhere in this system.
   *  Two things overlap by being printed out of register: the second impression
   *  sits one pitch down and right of the first, both fully opaque, both dated.
   *  The contract asks for exactly this when a `VerifierAgent` rebuild shows as
   *  a second impression beside the first. */
  misregistration: space.s1,
} as const;

/** GRID — the contract asks for plates set square across a strict grid, four up
 *  on desktop. Cells are square and the count is the frame's; the cell size is
 *  therefore a consequence of the frame rather than a fixed number, which is
 *  what keeps it from wrapping a hundred points narrower than its comp.
 *
 *  Phase 9 composes with these; Phase 8 may add a second count for tablet. */
export const grid = {
  gutter: space.s3,
  cellsPhone: 2,
  cellsDesktop: 4,
  /** Page margin. The phone gets one dense step, desktop one hard step. */
  marginPhone: space.s4,
  marginDesktop: space.s6,
  /** The fixed left rail on desktop: two steps of the scale wide. Sized from
   *  its contents — "WARDROBE" at the 30pt stencil sets ~100pt, and the SYSTEM
   *  STATUS plate's longest code line sets ~91pt in mono at 10/1.0 — plus a
   *  margin either side. */
  rail: space.s8 + space.s6,
  /** The frame boundary. Below this the phone composition; at or above it the
   *  desktop one. Tablet degrades between them (Phase 12). */
  desktopFrom: 900,
} as const;

/** MOTION GRAMMAR — a plate is either printed or it is not.
 *
 *  This world has no easing curves, and that absence is the token. Nothing
 *  tweens a value: no fade, no rise, no spring, no scale-in. What moves is a
 *  blade — a 45° cut that wipes a plate into or out of existence at constant
 *  speed, because a blade does not accelerate. Phase 11 orchestrates one
 *  authored moment per screen out of exactly this vocabulary; Phase 7 only
 *  supplies it.
 *
 *  This deliberately overrides the craft floor's default of an exponential
 *  ease-out from an already-visible state. The floor yields to a committed
 *  world, and an ease-out here would be the single most legible way to make the
 *  build look like every other app again. The floor's actual requirement — that
 *  content is visible by default and motion is enhancement — is met more
 *  strictly than by easing: with reduced motion on, `cut` is 0 and every plate
 *  is simply printed.
 *
 *  v1's 160/260/420 and its three cubic-bezier curves are gone; no value or
 *  curve here derives from them. */
export const motion = {
  /** The 45° wipe. The only animated transition in the world. */
  cut: 110,
  /** A plate arriving. Zero, and it is meant to be zero. */
  print: 0,
  /** Minimum separation between two prints in a sequence, so two SSE events
   *  landing in the same frame still read as two events rather than one. It is
   *  a floor, never a schedule — the five words are paced by the stream, and a
   *  fast response prints all five at once rather than faking a delay. */
  floor: 90,
  /** Degrees. Shared with `hazard.angle`: the strike and the wipe are the same
   *  gesture. */
  angle: 45,
  /** Constant speed. `Easing.linear`, expressed here so no screen reaches for
   *  a bezier out of habit. */
  easing: "linear",
} as const;

/** CONTENT COLOUR — the garment's own dye, and not part of the brand system.
 *
 *  `Color` in `backend/schemas/clothing.py` is a closed set of 18 values that
 *  the vision pass emits about the user's actual garment. Showing that colour
 *  is functionally necessary; it is product truth, not decoration, and it is
 *  quarantined here so it can never be mistaken for a system token. Nothing in
 *  the interface takes its colour from this map.
 *
 *  THE ORANGE COLLISION, resolved. `Color.ORANGE` is in the vocabulary, and
 *  safety orange is the system accent — an orange garment drawn in `tag.field`
 *  would read as a to-buy tag. So the dye orange is a dye orange (`#D2601A`,
 *  visibly duller and browner) and, more importantly, the rule below makes the
 *  question moot.
 *
 *  THE RULE: a dye chip is never colour alone. Every chip carries the material's
 *  hairline and its name set beneath it in mono, which is the same rule the
 *  contract already states for state. That is what lets `white` sit on the
 *  cotton ground and `black` on the nylon ground at all, and it is why no
 *  contrast floor applies to the swatches themselves.
 *
 *  `OTHER` is `null` on purpose: the pipeline is saying it could not name the
 *  colour, so the chip prints struck rather than guessing a grey. */
export const dye: Record<string, string | null> = {
  black: "#17161A",
  white: "#F6F3EC",
  red: "#C1272D",
  blue: "#1F5FA9",
  navy: "#16233F",
  green: "#2E7D4F",
  yellow: "#E8B310",
  orange: "#D2601A",
  pink: "#D94F82",
  purple: "#6B3FA0",
  brown: "#6B4A2F",
  grey: "#909093",
  beige: "#D6C3A5",
  cream: "#EFE4CC",
  maroon: "#6E1C2B",
  olive: "#5E6033",
  teal: "#16706E",
  other: null,
};
