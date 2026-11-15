/** The typed request — Plan v2 Phase 9.
 *
 *  Two presences, which is what the FIRST VIEWPORT blocks ask for. The field
 *  is a well — sunken, the one plane in the material system that is pressed
 *  into the ground rather than fastened onto it. The moment the shopper has
 *  typed something, the same words print above it as a stamped header plate,
 *  in quotes at display weight: the shopper's words frame the machine's, two
 *  ramp steps under them, and they never compete.
 *
 *  This is `useAppStore.userIntent`, which `useAnalysis` passes straight to
 *  `POST /analyze/stream?user_intent=…`. Nothing about it is decorative.
 */

import React from "react";
import { Platform, Text, TextInput, View } from "react-native";

import { dim, space, surface } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { type } from "../theme/type";
import { Code } from "./Margin";

export function IntentStamp({ text, desktop }: { text: string; desktop: boolean }) {
  const { material: m } = useTheme();
  if (!text.trim()) return null;

  return (
    <View style={{ marginBottom: space.s3 }}>
      <Text style={[desktop ? type.stampDesktop : type.stampPhone, { color: m.ink }]}>
        {`"${text.trim().toUpperCase()}"`}
      </Text>
      <Code style={{ marginTop: space.s1 }}>WHAT YOU ASKED FOR · SENT WITH THE PHOTOGRAPH</Code>
    </View>
  );
}

export function IntentField({
  value,
  onChange,
  onSubmit,
}: {
  value: string;
  onChange: (next: string) => void;
  onSubmit?: () => void;
}) {
  const { material: m } = useTheme();

  return (
    <View>
      <TextInput
        value={value}
        onChangeText={onChange}
        onSubmitEditing={onSubmit}
        returnKeyType="done"
        multiline={false}
        accessibilityLabel="Your request, in plain language"
        placeholder={'RAINY DINNER UNDER ₹5,000'}
        // Pre-composited dim rather than ink at an opacity, because a
        // TextInput placeholder takes a solid colour. 5.99:1 on the cotton
        // well, far past it on nylon's.
        placeholderTextColor={m.inkDim}
        selectionColor={m.ink}
        style={[
          type.plateValue,
          {
            backgroundColor: m.well,
            color: m.ink,
            borderWidth: surface.hairline,
            borderColor: m.strokeHeavy,
            borderRadius: surface.radius,
            paddingVertical: 13,
            paddingHorizontal: surface.platePadX,
            minHeight: 44,
            // The browser's own focus ring belongs to no design system.
            ...(Platform.OS === "web" ? ({ outlineStyle: "none" } as object) : null),
          },
        ]}
      />
      <Code style={{ marginTop: space.s1, opacity: dim }}>
        PLAIN LANGUAGE · OCCASION, WEATHER, A ₹ CAP · OPTIONAL
      </Code>
    </View>
  );
}
