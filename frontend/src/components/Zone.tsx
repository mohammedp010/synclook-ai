/** Zone heads — Plan v2 Phase 9.
 *
 *  "Wayfinding is reading — every zone carries its own quoted name." The
 *  quoted names are the ones Phase 8 fixed in `navigation/routes.ts` (`ZONE`),
 *  set in the display voice rather than labelled in UI type, with a 2pt rule
 *  under them and whatever state word the zone is currently in on the right.
 *
 *  The craft floor bans a kicker or eyebrow above a heading outright. A zone
 *  head is not one: it is the heading, in the world's own display face, and
 *  nothing sits above it.
 */

import React from "react";
import { Text, View } from "react-native";

import { space } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { type } from "../theme/type";

export function Zone({
  name,
  state,
  right,
  small,
  style,
}: {
  /** Already quoted — the `ZONE` constants carry their own quotation marks. */
  name: string;
  /** The zone's state, as a word. Printed in the margin under the rule. */
  state?: string;
  /** A plate that belongs to the zone head: a tag, a switch, an action. */
  right?: React.ReactNode;
  small?: boolean;
  style?: object;
}) {
  const { material: m } = useTheme();

  return (
    <View style={[{ marginBottom: space.s3 }, style]}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: space.s3 }}>
        <Text style={[small ? type.zoneSmall : type.zone, { color: m.ink, flexShrink: 1 }]}>
          {name}
        </Text>
        <View style={{ flex: 1 }} />
        {right}
      </View>
      <View style={{ height: 2, backgroundColor: m.strokeHeavy, marginTop: space.s1 }} />
      {state ? (
        <Text style={[type.code, { color: m.ink, opacity: 0.7, marginTop: space.s1 }]}>
          {state}
        </Text>
      ) : null}
    </View>
  );
}
