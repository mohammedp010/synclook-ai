/** The garment port — Plan v2 Phase 9.
 *
 *  The one raster slot in the build, and it belongs to the shopper: the
 *  photograph they took. Full-bleed from the top edge on the phone, no card
 *  and no radius, with the five words stencilled straight across it; a framed
 *  plate on desktop with the words set beneath rather than over.
 *
 *  Every other picture in v1 — the wardrobe illustration, the fold motif, the
 *  sparkle — is deleted and nothing refills the slot. This world is
 *  photograph, plate and tag.
 *
 *  The empty port is a designed state, not a dashed rectangle: it names what
 *  goes in it, in the same register as everything else on the surface.
 */

import React from "react";
import { Image, Text, View, type ViewStyle } from "react-native";

import { dim, space, surface } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { type } from "../theme/type";
import { Code } from "./Margin";
import { Screws } from "./Plate";

export function GarmentPort({
  uri,
  height,
  /** Printed across the top of the port: `"HELD"`, `"READING"`, `"READ"`. */
  state,
  /** What the port is showing, in the margin. */
  note,
  children,
  style,
}: {
  uri: string | null;
  height: number;
  state: string;
  note?: string;
  /** The stencilled words, when they sit over the photograph (phone). */
  children?: React.ReactNode;
  style?: ViewStyle;
}) {
  const { material: m } = useTheme();

  return (
    <View
      style={[
        {
          height,
          backgroundColor: m.well,
          borderWidth: surface.rule,
          borderColor: m.strokeHeavy,
          borderRadius: surface.radius,
          overflow: "hidden",
        },
        style,
      ]}
    >
      {uri ? (
        <Image
          source={{ uri }}
          accessibilityLabel="The garment you photographed"
          style={{ position: "absolute", left: 0, top: 0, right: 0, bottom: 0 }}
          resizeMode="cover"
        />
      ) : null}

      <Screws color={m.strokeHeavy} />

      {/* The port always says what it is holding, over the photograph or over
          the empty well, on a solid strip so the word survives any garment
          colour underneath it. */}
      <View
        style={{
          alignSelf: "flex-start",
          backgroundColor: m.ground,
          paddingVertical: 5,
          paddingHorizontal: 9,
          margin: space.s2,
        }}
      >
        <Text style={[type.plateTitle, { color: m.ink }]}>{state}</Text>
      </View>

      {children}

      {!uri ? (
        <View
          style={{
            position: "absolute",
            left: space.s3,
            right: space.s3,
            bottom: space.s3,
          }}
        >
          <Text style={[type.zoneSmall, { color: m.ink, opacity: dim }]}>
            {'"NO GARMENT HELD"'}
          </Text>
          <Code style={{ marginTop: 3 }}>
            ONE GARMENT, PHOTOGRAPHED FLAT OR WORN · JPEG FROM THE CAMERA OR THE LIBRARY
          </Code>
        </View>
      ) : null}

      {note ? (
        <View
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: m.ground,
            paddingVertical: 5,
            paddingHorizontal: 9,
          }}
        >
          <Code numberOfLines={1}>{note}</Code>
        </View>
      ) : null}
    </View>
  );
}
