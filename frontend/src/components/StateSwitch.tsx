/** State switches — Plan v2 Phase 9.
 *
 *  "State is a word (`"ON"` / `"OFF"` / `"HELD"`), never colour alone."
 *  Both controls below carry the store's real fields: `shoppingIntent`
 *  (menswear / womenswear / unisex / all) and `includeProducts`. v1 set these
 *  under tracked-out ALL-CAPS eyebrow labels — "SHOPPING INTENT" — which is
 *  the device the brief bans by name; here the switch's own selected position
 *  says what it is, and the margin line under it says what it will do.
 */

import React from "react";
import { Pressable, Text, View } from "react-native";

import { dim, space, surface } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { type } from "../theme/type";
import { Code } from "./Margin";
import { Screws } from "./Plate";

export function Selector<T extends string>({
  options,
  value,
  onChange,
  note,
  label,
}: {
  options: ReadonlyArray<readonly [T, string]>;
  value: T;
  onChange: (next: T) => void;
  note?: string;
  /** Screen-reader name for the group. Nothing is printed for it. */
  label: string;
}) {
  const { material: m } = useTheme();

  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={label}>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space.s1 }}>
        {options.map(([key, printed]) => {
          const on = key === value;
          return (
            <Pressable
              key={key}
              onPress={() => onChange(key)}
              accessibilityRole="radio"
              accessibilityState={{ selected: on }}
              accessibilityLabel={`${printed}, ${on ? "on" : "off"}`}
              style={({ pressed }) => ({
                borderWidth: on ? surface.rule : surface.hairline,
                borderColor: on ? m.strokeHeavy : m.stroke,
                backgroundColor: on ? m.label : "transparent",
                paddingVertical: 7,
                paddingHorizontal: 9,
                minHeight: 44,
                justifyContent: "center",
                opacity: pressed ? 0.6 : 1,
              })}
            >
              <Screws color={on ? m.strokeHeavy : m.stroke} />
              <Text style={[type.plateValue, { color: m.ink, opacity: on ? 1 : dim }]}>
                {printed}
              </Text>
              <Text style={[type.code, { color: m.ink, opacity: dim, marginTop: 2 }]}>
                {on ? '"ON"' : '"OFF"'}
              </Text>
            </Pressable>
          );
        })}
      </View>
      {note ? <Code style={{ marginTop: space.s1 }}>{note}</Code> : null}
    </View>
  );
}

/** A two-position switch that prints both its state and its consequence. */
export function WordSwitch({
  name,
  on,
  onChange,
  whenOn,
  whenOff,
}: {
  name: string;
  on: boolean;
  onChange: (next: boolean) => void;
  whenOn: string;
  whenOff: string;
}) {
  const { material: m } = useTheme();

  return (
    <Pressable
      onPress={() => onChange(!on)}
      accessibilityRole="switch"
      accessibilityState={{ checked: on }}
      accessibilityLabel={`${name}, ${on ? "on" : "off"}. ${on ? whenOn : whenOff}`}
      style={({ pressed }) => ({
        borderWidth: surface.hairline,
        borderColor: m.stroke,
        paddingVertical: 7,
        paddingHorizontal: 9,
        minHeight: 44,
        justifyContent: "center",
        opacity: pressed ? 0.6 : 1,
      })}
    >
      <Screws color={m.stroke} />
      <View style={{ flexDirection: "row", alignItems: "baseline", gap: space.s2 }}>
        <Text style={[type.plateValue, { color: m.ink }]}>{name}</Text>
        <Text style={[type.plateTitle, { color: m.ink }]}>{on ? '"ON"' : '"OFF"'}</Text>
      </View>
      <Text style={[type.code, { color: m.ink, opacity: dim, marginTop: 2 }]}>
        {on ? whenOn : whenOff}
      </Text>
    </Pressable>
  );
}
