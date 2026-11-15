/** Actions — Plan v2 Phase 9.
 *
 *  The primary action is a full-width orange plate, foot-pinned on the phone
 *  and at the top of the read pane on desktop. v1's only button shape was a
 *  `borderRadius: 9999` capsule and its hierarchy was fill-versus-outline;
 *  here the shape is the plate, the hierarchy is the field, and the state is a
 *  word.
 *
 *  Touch targets clear 44pt on every surface: the action plate's own padding
 *  makes 45, and the secondary plate declares a `minHeight`.
 */

import React from "react";
import { Pressable, Text, View, type ViewStyle } from "react-native";

import { dim, space, surface, tag } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { type } from "../theme/type";
import { Screws } from "./Plate";

export function ActionPlate({
  label,
  note,
  onPress,
  disabled,
  style,
}: {
  /** The action, named as the action. Never arrow-suffixed. */
  label: string;
  /** A code line printed under the label — what the action will actually do. */
  note?: string;
  onPress: () => void;
  disabled?: boolean;
  style?: ViewStyle;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      accessibilityLabel={note ? `${label}. ${note}` : label}
      style={({ pressed }) => [
        {
          backgroundColor: tag.field,
          paddingVertical: surface.actionPadY,
          paddingHorizontal: surface.actionPadX,
          opacity: disabled ? 0.45 : pressed ? 0.85 : 1,
          minHeight: 44,
          justifyContent: "center",
        },
        style,
      ]}
    >
      <Screws color={tag.ink} />
      <Text style={[type.action, { color: tag.ink, textAlign: "center" }]}>{label}</Text>
      {note ? (
        <Text style={[type.code, { color: tag.ink, textAlign: "center", marginTop: 4 }]}>
          {note}
        </Text>
      ) : null}
    </Pressable>
  );
}

/** The second action on a surface: same plate, no field. The world has one
 *  hue and it is spent on the thing being tagged, so a secondary action is
 *  ink on the ground. */
export function SecondaryPlate({
  label,
  onPress,
  heavy,
  disabled,
  style,
}: {
  label: string;
  onPress: () => void;
  heavy?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
}) {
  const { material: m } = useTheme();
  const line = heavy ? m.strokeHeavy : m.stroke;

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      style={({ pressed }) => [
        {
          borderWidth: surface.hairline,
          borderColor: line,
          borderRadius: surface.radius,
          paddingVertical: surface.platePadY,
          paddingHorizontal: surface.platePadX,
          minHeight: 44,
          justifyContent: "center",
          opacity: disabled ? 0.45 : pressed ? 0.6 : 1,
        },
        style,
      ]}
    >
      <Screws color={line} />
      <Text style={[type.plateTitle, { color: m.ink, textAlign: "center" }]}>{label}</Text>
    </Pressable>
  );
}

/** The material switch — the two-theme mechanism's user-facing control, which
 *  is product truth and survives. It names the material it will print in, so
 *  the control is a word rather than a sun-and-moon icon. */
export function MaterialSwitch({ style }: { style?: ViewStyle }) {
  const { themeName, material: m, toggleTheme } = useTheme();
  /** Named off `themeName`, never off the material this control happens to be
   *  printed in. The rail prints in the counter material, so reading `m.name`
   *  made the rail's switch name the rail and the plane's switch name the
   *  plane — two controls, one state, two different words for it. Caught on
   *  screen: the phone read `BLACK NYLON / SWITCH TO COTTON`. */
  const current = themeName === "dark" ? "BLACK NYLON" : "WHITE COTTON";
  const other = themeName === "dark" ? "WHITE COTTON" : "BLACK NYLON";

  return (
    <Pressable
      onPress={toggleTheme}
      accessibilityRole="switch"
      accessibilityState={{ checked: themeName === "dark" }}
      accessibilityLabel={`Material. Currently ${current}. Switch to ${other}.`}
      style={({ pressed }) => [
        {
          borderWidth: surface.hairline,
          borderColor: m.strokeHeavy,
          paddingVertical: 7,
          paddingHorizontal: 9,
          minHeight: 44,
          flexShrink: 1,
          justifyContent: "center",
          opacity: pressed ? 0.6 : 1,
        },
        style,
      ]}
    >
      <Screws color={m.strokeHeavy} />
      {/* The state word alone. `MATERIAL "WHITE COTTON"` overran the phone
          head strip and clipped; the note below already says what the control
          does, so the title only has to say what is true now. */}
      <Text style={[type.plateTitle, { color: m.ink }]} numberOfLines={1}>
        {`"${current}"`}
      </Text>
      <View style={{ flexDirection: "row", gap: space.s1, marginTop: 3 }}>
        <Text style={[type.code, { color: m.ink, opacity: dim }]}>{`SWITCH TO ${other}`}</Text>
      </View>
    </Pressable>
  );
}
