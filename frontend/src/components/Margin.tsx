/** The margins — Plan v2 Phase 9.
 *
 *  DENSITY 8. The direction's raised hand (the Info-Noise Sleeve) asked the
 *  margins to carry real lot, confidence, ₹ and source codes instead of
 *  whitespace — "that sleeve's density with none of its fiction". So every
 *  code line in this build reads a value that exists: a `request_id`, a
 *  confidence head, a ₹ price from a `ProductLink`, a `wardrobe_item_id`, a
 *  stage name the stream emitted.
 *
 *  `Code` is the only place small mono type is set. It floors at `dim` 0.7,
 *  which measures 7.57:1 on cotton and 8.97:1 on nylon; there is no second,
 *  dimmer tier.
 */

import React from "react";
import { Text, View, type TextStyle, type ViewStyle } from "react-native";

import { dim, space } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { type } from "../theme/type";

export function Code({
  children,
  full,
  style,
  numberOfLines,
}: {
  children: React.ReactNode;
  /** Full-strength ink — a code the reader must act on, not a margin note. */
  full?: boolean;
  style?: TextStyle | TextStyle[];
  numberOfLines?: number;
}) {
  const { material: m } = useTheme();
  return (
    <Text
      numberOfLines={numberOfLines}
      style={[type.code, { color: m.ink, opacity: full ? 1 : dim }, style as TextStyle]}
    >
      {children}
    </Text>
  );
}

/** A stack of code lines, the margin's usual shape. Blank entries are dropped
 *  rather than printed as an empty row. */
export function CodeBlock({
  lines,
  style,
}: {
  lines: Array<string | null | undefined | false>;
  style?: ViewStyle;
}) {
  const kept = lines.filter((l): l is string => Boolean(l));
  return (
    <View style={style}>
      {kept.map((line, i) => (
        <Code key={line + i} style={i === 0 ? undefined : { marginTop: 2 }}>
          {line}
        </Code>
      ))}
    </View>
  );
}

/** A named value on one line: the name in the margin register, the value at
 *  full strength. State is a word in this world, so the value is a word or a
 *  figure — never a coloured dot. */
export function CodeRow({
  name,
  value,
  nameWidth = 88,
}: {
  name: string;
  value: string;
  nameWidth?: number;
}) {
  return (
    <View style={{ flexDirection: "row", marginTop: 2 }}>
      <Code style={{ width: nameWidth }}>{name}</Code>
      <Code full style={{ flex: 1 }}>
        {value}
      </Code>
    </View>
  );
}

/** A 2pt rule. The zone separator and the plane divider. */
export function Rule({ heavy, style }: { heavy?: boolean; style?: ViewStyle }) {
  const { material: m } = useTheme();
  return (
    <View
      style={[
        { height: 2, backgroundColor: heavy ? m.strokeHeavy : m.stroke, marginVertical: space.s2 },
        style,
      ]}
    />
  );
}
