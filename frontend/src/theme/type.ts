/** Typographic identity — Plan v2 Phase 6.
 *
 *  Three faces, chosen as objects from the locked world (surface brief
 *  `.impeccable/surfaces/frontend.md`, form `Industrial Quote Grammar`), not
 *  from a pairing habit. Each was set in the app's own words — the five quoted
 *  attributes, the ₹ figures, the plate labels — on both material grounds
 *  before it was picked.
 *
 *  BIG SHOULDERS DISPLAY 900 — the display voice. Patric King's condensed
 *    gothic drawn from Chicago's industrial signage: flat sides, cut terminals,
 *    squared bowls. It is the face the world's stencilled plates are already
 *    set in. Beat Anton (the default poster gothic, one weight, no hierarchy),
 *    Saira Condensed (rounded, reads sportswear), Barlow Condensed (soft
 *    terminals, reads app), Antonio (too light at display weight) and Archivo
 *    Black (not condensed) in a rendered round.
 *
 *  MARTIAN MONO — the UI voice, mono caps on plates and in the margins.
 *    Evil Martians' semi-condensed engineered mono: it is the narrowest of the
 *    candidates, which is what lets a tracked-out caps plate survive a 390pt
 *    frame, and its flat terminals answer the display face. Beat Azeret Mono
 *    and Chivo Mono, both wider and softer. Space Mono and IBM Plex Mono are
 *    banned by name; JetBrains/Geist are code-editor defaults, not this world.
 *
 *  ARCHIVO 400/500 — the plain upright at small size. Hector Gatti's grotesque
 *    for Omnibus-Type, drawn for highway signage and newsprint, which is the
 *    same utilitarian lineage as the other two and holds up on the black-nylon
 *    ground. Beat Public Sans (the neutral-sans register the brief bans),
 *    Barlow (thin on dark) and Saira (rounded, techy descenders).
 *
 *  All three are SIL Open Font License 1.1, verified from the `name` table of
 *  the shipped binaries rather than from a directory listing. OFL 1.1 permits
 *  embedding in an application and serving over the web; the licence is
 *  recorded in the surface brief with designer, foundry and version.
 *
 *  React Native resolves a weight by family *name*, not by `fontWeight`, so
 *  every weight below is a separate asset and a separate family string. Six
 *  assets, ~546 KB total, is the whole budget — a seventh needs an argument.
 *
 *  `tailwind.config.js` carries a hand-copy of `families` and `sizes`. That
 *  file is plain CommonJS and cannot import this module, so the two must stay
 *  byte-identical; change them together or NativeWind and StyleSheet drift.
 */

import {
  Archivo_400Regular,
  Archivo_500Medium,
} from "@expo-google-fonts/archivo";
import {
  BigShouldersDisplay_700Bold,
  BigShouldersDisplay_900Black,
} from "@expo-google-fonts/big-shoulders-display";
import {
  MartianMono_400Regular,
  MartianMono_700Bold,
} from "@expo-google-fonts/martian-mono";

/** The map `expo-font`'s `useFonts` is handed in `App.tsx`. The keys become
 *  the `fontFamily` strings below, which is why they are not renamed. */
export const fontAssets = {
  BigShouldersDisplay_900Black,
  BigShouldersDisplay_700Bold,
  MartianMono_400Regular,
  MartianMono_700Bold,
  Archivo_400Regular,
  Archivo_500Medium,
} as const;

/** Family strings, named for what they do in this world rather than for the
 *  typeface, so a face can be replaced without rewriting every screen. */
export const families = {
  /** Stencilled display caps — the machine's words, the zone names. */
  stencil: "BigShouldersDisplay_900Black",
  /** Display at small sizes, where 900 fills in and goes muddy. */
  stencilMid: "BigShouldersDisplay_700Bold",
  /** Mono on plates and in the margins: codes, figures, state words. */
  plate: "MartianMono_400Regular",
  /** Mono at emphasis: plate titles, the primary action, `"YOURS"`. */
  plateBold: "MartianMono_700Bold",
  /** Plain upright, running text only. */
  text: "Archivo_400Regular",
  /** Plain upright, emphasis inside running text. */
  textMid: "Archivo_500Medium",
} as const;

/** Two ramps, because this world has two registers and no middle.
 *
 *  The display ramp steps by ~1.385 — hard jumps, so a stencilled word is
 *  never *slightly* larger than the one under it. The text ramp steps by ~1.1,
 *  dense label increments, which is what carries the margin density the
 *  direction contract asks for (real lot, confidence, ₹ and source codes where
 *  a calmer world would leave whitespace).
 *
 *  Deliberately not 12/14/16/20/24/32/48: that ladder is v1's, and a scale
 *  inherited from the rejected build is the rejected build's rhythm. */
export const sizes = {
  /** Display ramp. `d4` is the phone's stencil over the photograph, `d5` its
   *  desktop counterpart set beside the image.
   *
   *  The ramp stops at 80 because the vocabulary stops it. The vision pass
   *  emits a closed set (`backend/schemas/clothing.py`), and its longest
   *  tokens are `STREETWEAR` and `MINIMALIST`. Measured in the shipped binary,
   *  `"STREETWEAR"` sets 323pt at 58 and 446pt at 80, against 350pt of usable
   *  width on a 390pt phone: 58 is the largest step the real words survive,
   *  and anything above 80 has no frame to live in at either size. A step
   *  above that would exist only to be avoided. */
  d1: 22,
  d2: 30,
  d3: 42,
  d4: 58,
  d5: 80,
  /** Text ramp, mono and upright both. */
  t1: 10,
  t2: 11,
  t3: 12,
  t4: 13,
  t5: 15,
  t6: 17,
} as const;

type Ramp = typeof sizes;

/** `letterSpacing` in React Native is absolute points, not ems, so every role
 *  computes its own from a ratio. Rounded to a tenth: sub-tenth precision is
 *  invisible and makes the Tailwind hand-copy harder to verify. */
const track = (size: number, em: number) => Math.round(size * em * 10) / 10;
const leading = (size: number, ratio: number) => Math.round(size * ratio);

export interface TypeRole {
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
  letterSpacing: number;
  textTransform?: "uppercase";
}

const stencil = (key: keyof Ramp, em = -0.01): TypeRole => ({
  fontFamily: families.stencil,
  fontSize: sizes[key],
  // 0.86 — stacked display words read as one block, the way a stencil set
  // sits on a crate. Single-line display uses `zone`/`stamp` instead.
  lineHeight: leading(sizes[key], 0.86),
  letterSpacing: track(sizes[key], em),
  textTransform: "uppercase",
});

const monoCaps = (key: keyof Ramp, em: number, bold = false): TypeRole => ({
  fontFamily: bold ? families.plateBold : families.plate,
  fontSize: sizes[key],
  lineHeight: leading(sizes[key], 1.15),
  letterSpacing: track(sizes[key], em),
  textTransform: "uppercase",
});

/** The roles screens actually reach for. A screen that needs a size not on
 *  this list is describing a role this world has not named yet — add it here
 *  with its reason, rather than setting `fontSize` inline. */
export const type = {
  /** The five quoted attribute words, stencilled across the user's photograph.
   *  Phone frame. */
  stencilPhone: stencil("d4"),
  /** The same words on desktop, set beside the photograph on their own plates. */
  stencilDesktop: stencil("d5"),
  /** The stamped header plate carrying the intent the shopper typed. It sits
   *  a full two steps under the stencil at either frame: the shopper's words
   *  frame the machine's, they do not compete with them. */
  stampPhone: stencil("d2"),
  stampDesktop: stencil("d3"),
  /** Quoted zone names — wayfinding is reading, so every zone is set in the
   *  display voice rather than labelled in UI type. */
  zone: stencil("d2", 0),
  /** Display at its floor, where 900 closes up: the 700 weight instead. */
  zoneSmall: { ...stencil("d1", 0), fontFamily: families.stencilMid },

  /** Mono caps inside a plate: `"YOURS"`, `"TO BUY"`, `"HELD"`. State is a
   *  word in this world, never colour alone, so this role carries state. */
  plateTitle: monoCaps("t3", 0.14, true),
  /** Mono caps, plate body: attribute name plus its confidence figure. */
  plateValue: monoCaps("t3", 0.08),
  /** The margins: lot, source, ₹ cap, rebuild count, system status. */
  code: monoCaps("t1", 0.1),
  /** A confidence figure standing alone under a stencilled word. */
  figure: monoCaps("t2", 0.06),
  /** The primary action plate. Tracked wide because the plate is wide. */
  action: monoCaps("t4", 0.16, true),

  /** Running text. 1.55 leading at 13pt, 1.6 at 15pt — the upright is the only
   *  place this world lets a line breathe. */
  body: {
    fontFamily: families.text,
    fontSize: sizes.t5,
    lineHeight: leading(sizes.t5, 1.6),
    letterSpacing: 0,
  } as TypeRole,
  bodySmall: {
    fontFamily: families.text,
    fontSize: sizes.t4,
    lineHeight: leading(sizes.t4, 1.55),
    letterSpacing: 0,
  } as TypeRole,
  bodyStrong: {
    fontFamily: families.textMid,
    fontSize: sizes.t5,
    lineHeight: leading(sizes.t5, 1.6),
    letterSpacing: 0,
  } as TypeRole,
} as const;

/** Archivo averages ~0.5em per character, so 68ch of running text is ~510pt.
 *  Measure is a hard cap on any upright column, at either frame. */
export const bodyMeasure = Math.round(sizes.t5 * 0.5 * 68);
