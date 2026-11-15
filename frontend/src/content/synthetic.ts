/** The worked read — Plan v2 Phase 9.
 *
 *  Phase 8 deleted v1's Landing screen and refused to relocate its job. The
 *  cold-open risk Landing was badly covering — a first visitor facing an empty
 *  capture surface — is answered here instead: the `empty` phase carries one
 *  complete read at production fidelity, so the machine's five quoted words
 *  land on a real garment before the visitor gives it theirs.
 *
 *  HONESTY RULES THIS FILE OBEYS.
 *
 *  - It derives from `src/api/__mocks__/mockAnalysis.ts`, which the surface
 *    brief names as the honest source for demonstration data. That file is
 *    product truth and is not edited; this one extends it for the surface.
 *  - Every screen that renders it prints `"SYNTHETIC"` next to it. A visitor
 *    can never mistake it for a reading of their own garment.
 *  - The product listings, prices, retailers and ₹ figures are the mock's
 *    own — Indian market, real retailers, plausible prices.
 *  - It makes no commercial claim of any kind. There is no user count, no
 *    usage figure, no testimonial, no logo, no uptime and no press. PRODUCT.md
 *    marks all of those unfabricable and nothing here goes near them.
 *  - The confidence figures are the one thing added rather than inherited: the
 *    mock carries `confidence` only, and the surface has to show four heads
 *    across five slots. They are demonstration values on demonstration data,
 *    inside the block labelled synthetic.
 */

import { MOCK_ANALYSIS } from "../api/__mocks__/mockAnalysis";
import type {
  ClothingAttributes,
  RecommendationItem,
  StreamAnalysisResult,
  WardrobeItem,
} from "../types/api";

/** Printed wherever any of this is on screen. */
export const SYNTHETIC = '"SYNTHETIC"';

/** The request the shopper would have typed. Plain language, an occasion and
 *  a ₹ cap — the shape PRODUCT.md gives as the example, and the cap the
 *  flagged claim below is measured against. */
export const SYNTHETIC_INTENT = "weekend out under ₹5,000";

const base = MOCK_ANALYSIS.detected_attributes;

/** Five slots, four heads. `secondary_color` is `string | null` in
 *  `src/types/api.ts` and null here, which makes the contract's struck `"—"`
 *  plate the routine reading it actually is rather than an edge case. */
export const SYNTHETIC_ATTRIBUTES: ClothingAttributes = {
  ...base,
  color_confidence: 0.81,
  pattern_confidence: 0.74,
  style_confidence: 0.66,
};

const mockItems = MOCK_ANALYSIS.recommendations[0].items;
const jeans = mockItems.find((i) => i.item_type === "jeans")!;
const sneakers = mockItems.find((i) => i.item_type === "sneakers")!;

/** The wardrobe comes first: two of the three pieces are already owned and are
 *  marked before anything is billed, which is the product's second
 *  differentiator and the reason the outfit grid leads with `"YOURS"`.
 *  An owned piece carries no product listing, because the real pipeline skips
 *  the shopping stage for a slot the closet already covered. */
const SYNTHETIC_ITEMS: RecommendationItem[] = [
  {
    item_type: jeans.item_type,
    color: jeans.color,
    style: jeans.style,
    reason: jeans.reason,
    owned: true,
    wardrobe_item_id: "wd-0112",
    products: [],
  },
  {
    item_type: "overshirt",
    color: "olive",
    style: "casual",
    reason: "An olive overshirt layers over navy without fighting it.",
    owned: true,
    wardrobe_item_id: "wd-0087",
    products: [],
  },
  {
    // The one slot the closet could not fill, so shopping covered it — and
    // the verifier flagged it against the ₹5,000 cap in the typed request.
    ...sneakers,
    owned: false,
  },
];

/** The flagged claim. This is the only thing in the build that can turn on the
 *  hazard tape, and it is shaped exactly like a real
 *  `StreamAnalysisResult.errors` entry, because that is where a live run's
 *  flag arrives from. */
export const SYNTHETIC_FLAG =
  "verifier: budget claim not verified — ₹7,495 is above the ₹5,000 cap in your request";

export const SYNTHETIC_READ: StreamAnalysisResult = {
  request_id: MOCK_ANALYSIS.request_id,
  detected_attributes: SYNTHETIC_ATTRIBUTES,
  recommendations: [
    {
      ...MOCK_ANALYSIS.recommendations[0],
      items: SYNTHETIC_ITEMS,
    },
  ],
  errors: [SYNTHETIC_FLAG],
};

/** The legend for the `"YOURS"` marks above. Two of these are the pieces the
 *  synthetic outfit matched; the other two are what makes it a closet rather
 *  than a list of two. */
export const SYNTHETIC_WARDROBE: WardrobeItem[] = [
  {
    id: "wd-0112",
    label: "White jeans",
    clothing_type: "jeans",
    color: "white",
    pattern: "solid",
    style: "casual",
    created_at: null,
  },
  {
    id: "wd-0087",
    label: "Olive overshirt",
    clothing_type: "overshirt",
    color: "olive",
    pattern: "solid",
    style: "casual",
    created_at: null,
  },
  {
    id: "wd-0201",
    label: "Black chinos",
    clothing_type: "chinos",
    color: "black",
    pattern: "solid",
    style: "smart_casual",
    created_at: null,
  },
  {
    id: "wd-0155",
    label: "Grey sweatshirt",
    clothing_type: "sweatshirt",
    color: "grey",
    pattern: "solid",
    style: "casual",
    created_at: null,
  },
];
