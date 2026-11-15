/** Flow architecture — Plan v2 Phase 8.
 *
 * The route graph, re-derived from the task rather than inherited. v1 had six
 * routes; this has one working surface and two layers over it. The written IA
 * and the argument for each decision live in `.impeccable/surfaces/frontend.md`
 * under "Flow architecture"; this module is that document's machine-readable
 * half and the two must not drift apart.
 *
 * Types and vocabulary only. No screens: Phase 9 mounts these.
 */

/** One card, two layers.
 *
 * `Read` is the whole act — hold a garment, watch it read, stand the outfit up
 * beside it. v1 split that across Camera → Analysis → Results, and its own code
 * disagreed with the split: `Camera` was registered but unreachable, and
 * `Analysis` called `replace("Results")`, so it was never in the back stack. A
 * phase that deletes itself on exit was never a destination.
 *
 * `imageUri` is v1's `Analysis: { imageUri }` parameter with its meaning intact
 * — the URI of a garment handed to the reading surface. It is optional here
 * because `Read` is also the cold open, which `Analysis` never was.
 */
export type RootStackParamList = {
  Read: { imageUri?: string } | undefined;
  Wardrobe: undefined;
  PreviousReads: undefined;
};

/** Phases of the reading surface. Not routes — `useAnalysis` already owns this
 *  state machine (`idle | analyzing | done | error`) and v1 duplicated it into
 *  the route graph, where the two could disagree.
 *
 *  `held` is the one phase the hook has no status for: a photograph chosen but
 *  not yet sent. It is what the direction contract's foot-pinned
 *  `"READ A GARMENT"` plate acts on — a primary action on the surface that
 *  already holds the photograph only makes sense if the photograph can be held
 *  before it is read. It also stops a mis-picked frame from burning a full
 *  pipeline run, which v1's pick-and-go path could not.
 */
export type ReadPhase = "empty" | "held" | "reading" | "read" | "struck";

/** Flow order is preserved: photograph → read → outfit. `held` does not add a
 *  required step — the intent field is live in `empty` too, so typing first and
 *  shooting first both reach `reading`, and neither is mandated. */
export function readPhase(
  status: "idle" | "analyzing" | "done" | "error",
  hasImage: boolean
): ReadPhase {
  switch (status) {
    case "analyzing":
      return "reading";
    case "done":
      return "read";
    case "error":
      return "struck";
    case "idle":
      return hasImage ? "held" : "empty";
  }
}

/** Wayfinding is reading, so every zone carries its own quoted name and the
 *  desktop rail lists these rather than routes. Two are panes of the main
 *  plane, two are layers, one is permanent apparatus. */
export const ZONE = {
  read: '"THE READ"',
  outfit: '"THE OUTFIT"',
  wardrobe: '"THE WARDROBE"',
  previousReads: '"PREVIOUS READS"',
  systemStatus: '"SYSTEM STATUS"',
} as const;

/** The seven stages `useAnalysis` actually streams, in the order the graph
 *  emits them, with the word each prints while running. The contract asks the
 *  wait to move through named phases with text equivalents; these are the
 *  names, and they are the pipeline's own, not a narration written over it.
 *  The planner skips `wardrobe` and `shopping` at runtime, so a stage absent
 *  from a run is absent from the plate rather than shown pending. */
export const STAGE_WORD: Record<string, string> = {
  intent: '"READING THE REQUEST"',
  vision: '"READING THE GARMENT"',
  styling: '"MATCHING"',
  recommendation: '"BUILDING"',
  wardrobe: '"CHECKING WHAT YOU OWN"',
  shopping: '"PRICING"',
  verifier: '"CHECKING THE CLAIMS"',
};

/** Web paths. One route graph serves both frames, so there is one path set.
 *
 *  v1 had no linking configuration and no `scheme` in `app.json`, so no deep
 *  link shape existed to preserve — this defines the first one. Paths are web
 *  only for now; native prefixes need a `scheme`, which is a Phase 15 call.
 *
 *  A live read is not addressable and deliberately so: a URL that claims to
 *  restore a stream mid-flight would be fiction, since the stream cannot be
 *  resumed. `/read` addresses the surface, not a moment inside it.
 */
export const linkingConfig = {
  screens: {
    Read: "read",
    Wardrobe: "wardrobe",
    PreviousReads: "previous-reads",
  },
} as const;
