/** The five words — Plan v2 Phase 9, and the thing the whole direction is for.
 *
 *  THESIS: "the app says the obvious out loud, in straight quotation marks,
 *  because naming the obvious is literally what the vision pass does." The
 *  words here are `ClothingAttributes`' five fields and nothing else; the
 *  quotation marks are load-bearing, which is the only thing that keeps this
 *  world from being cosplay of a fashion house.
 *
 *  TWO FINDINGS FROM PHASES 6 AND 7 ARE SETTLED HERE.
 *
 *  1. WHERE THE CONFIDENCE FIGURE SITS WHEN THE WORD WRAPS. `SMART CASUAL`
 *     sets wider than the ramp's longest single token and wraps to two lines
 *     at d4 on a 390pt frame. So the figure is not trailing the word on its
 *     baseline — it is a fixed column on the right, and the figure sits on the
 *     *first* line of its word. A word that wraps pushes nothing.
 *
 *  2. FOUR HEADS, FIVE SLOTS. `ClothingAttributes` carries `confidence`,
 *     `color_confidence`, `pattern_confidence` and `style_confidence`.
 *     `secondary_color` has no head of its own — it shares the colour head.
 *     Printing a figure against it would invent a fifth measurement, and
 *     printing nothing would read as "unmeasured". So the two colour words are
 *     tied: a hairline bracket runs down the figure column from the colour
 *     figure to the secondary word, and the secondary row's column reads
 *     `ONE HEAD` rather than a number. The tie is drawn, so the claim is
 *     visible rather than explained in a footnote.
 */

import React from "react";
import { Text, View } from "react-native";

import { dim, space, surface } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { type } from "../theme/type";

/** The figure column. Sized from its widest real content — `ONE HEAD` set in
 *  Martian Mono at 10pt with 1pt of tracking. */
const FIGURE_COL = 74;

export interface WordRow {
  /** The attribute's field name, printed in the margin: COLOUR, PATTERN… */
  head: string;
  /** The machine's word, unquoted — this component adds the quotes. `null`
   *  means the pass returned nothing for the slot, which prints struck. */
  word: string | null;
  /** 0–1 from the matching confidence head, or `null` where there is none. */
  confidence?: number | null;
  /** This row shares the row above's confidence head. */
  tied?: boolean;
  /** Not yet arrived on the stream. Prints held, not blank. */
  waiting?: boolean;
}

export function WordStack({
  rows,
  size,
  style,
}: {
  rows: WordRow[];
  /** The display role — `stencilPhone` (58) over the photograph, or
   *  `stencilDesktop` (80) while the read owns the whole plane. */
  size: typeof type.stencilPhone;
  style?: object;
}) {
  const { material: m } = useTheme();

  return (
    <View style={style} accessibilityRole="list">
      {rows.map((row, i) => {
        const held = row.word === null || row.waiting;
        /** A slot the machine read as empty prints the word NONE, not a dash.
         *  Reviewed on screen: the display face's em dash sets low and short
         *  inside straight quotes and reads as an underscore, i.e. as damage
         *  rather than as a value. NONE is also the more honest reading —
         *  `secondary_color: null` means the vision pass found no second
         *  colour, which is a result, not an absence of one. The dash is kept
         *  for a slot that has not arrived yet, where nothing is known. */
        const label = row.waiting ? "WAITING" : row.word === null ? "NONE READ" : null;
        const printed = row.waiting ? "—" : (row.word ?? "NONE");

        return (
          <View
            key={`${row.head}-${i}`}
            style={{ flexDirection: "row", alignItems: "flex-start", marginBottom: space.s1 }}
            accessibilityRole="text"
            accessibilityLabel={
              row.word
                ? `${row.head}: ${row.word}${
                    row.confidence != null ? `, confidence ${row.confidence.toFixed(2)}` : ""
                  }`
                : `${row.head}: ${label}`
            }
          >
            <View style={{ flex: 1 }}>
              <Text
                style={[
                  size,
                  { color: m.ink, opacity: held ? dim : 1 },
                ]}
              >
                {`"${printed}"`}
              </Text>
            </View>

            <View style={{ width: FIGURE_COL, paddingTop: Math.round(size.fontSize * 0.22) }}>
              {row.tied ? (
                <Tie />
              ) : (
                <Text style={[type.figure, { color: m.ink }]}>
                  {row.confidence != null ? row.confidence.toFixed(2) : label ?? "—"}
                </Text>
              )}
              <Text style={[type.code, { color: m.ink, opacity: dim, marginTop: 2 }]}>
                {row.tied ? "ONE HEAD" : row.head}
              </Text>
              {label && !row.tied ? (
                <Text style={[type.code, { color: m.ink, opacity: dim, marginTop: 2 }]}>
                  {label}
                </Text>
              ) : null}
            </View>
          </View>
        );
      })}
    </View>
  );
}

/** The bracket that ties the secondary colour word to the colour head above
 *  it. A hairline up-tick into the previous row plus a horizontal foot — drawn
 *  geometry, not a glyph. */
function Tie() {
  const { material: m } = useTheme();
  return (
    <View style={{ height: 14, justifyContent: "flex-end" }}>
      <View
        style={{
          position: "absolute",
          left: 0,
          top: -18,
          width: surface.hairline,
          height: 28,
          backgroundColor: m.ink,
        }}
      />
      <View style={{ width: 9, height: surface.hairline, backgroundColor: m.ink }} />
    </View>
  );
}
