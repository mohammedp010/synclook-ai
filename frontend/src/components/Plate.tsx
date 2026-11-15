/** The plate — Plan v2 Phase 9, the form's base object.
 *
 *  OWN-WORLD: "Every label is a plate: square-cornered block, hairline stroke,
 *  four corner screws, mono caps inside." Nothing in this build is a card:
 *  there is no radius, no shadow and no elevation scale (material.ts
 *  `surface`). The screws are the tell — they say the block was fastened to
 *  the ground rather than floating above it.
 *
 *  A plate is struck rather than omitted when the machine has nothing: one
 *  45° rule corner to corner, the same gesture as the hazard tape and the
 *  motion grammar's blade, at a third scale.
 */

import React from "react";
import { StyleSheet, View, type ViewStyle } from "react-native";

import { surface } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";

export interface PlateProps {
  children?: React.ReactNode;
  /** Fill the plate with a plane of the material, or the tag field. */
  fill?: string;
  /** Load-bearing: full-strength ink stroke instead of the hairline. */
  heavy?: boolean;
  /** Two-point rule instead of a hairline — a zone frame, the garment port. */
  ruled?: boolean;
  /** The machine had nothing for this slot. Printed and struck, never dropped. */
  struck?: boolean;
  /** The one wide plate in the world: the primary action. */
  wide?: boolean;
  /** No interior padding — the plate is a frame around something else. */
  bare?: boolean;
  /** Stroke override, for a plate printed on the tag field. */
  stroke?: string;
  style?: ViewStyle | ViewStyle[];
}

export function Plate({
  children,
  fill,
  heavy,
  ruled,
  struck,
  wide,
  bare,
  stroke,
  style,
}: PlateProps) {
  const { material: m } = useTheme();
  const line = stroke ?? (heavy || ruled ? m.strokeHeavy : m.stroke);

  return (
    <View
      style={[
        styles.plate,
        ruled ? { borderWidth: surface.rule } : null,
        wide ? styles.wide : null,
        bare ? styles.bare : null,
        { borderColor: line, backgroundColor: fill ?? "transparent" },
        style as ViewStyle,
      ]}
    >
      <Screws color={line} />
      {children}
      {struck ? <Strike color={line} /> : null}
    </View>
  );
}

/** Four corner screws, inset by their own width. Drawn, never a border-radius
 *  and never an icon font. */
export function Screws({ color }: { color: string }) {
  const i = surface.screwInset;
  return (
    <>
      {(
        [
          { left: i, top: i },
          { right: i, top: i },
          { left: i, bottom: i },
          { right: i, bottom: i },
        ] as const
      ).map((pos, n) => (
        <View key={n} pointerEvents="none" style={[styles.screw, pos, { backgroundColor: color }]} />
      ))}
    </>
  );
}

/** A single 45° rule across the plate, clipped to it.
 *
 *  It was corner-to-corner — `atan2(h, w)` — which is 45° only on a square.
 *  On the outfit pane's `"NOT BUILT YET"` plate, 638 by 46, that resolved to
 *  4°: a near-horizontal rule laid through the middle of the sentence, which
 *  read as a rendering fault and struck out the words it was meant to frame.
 *  The angle is the world's one angle — the hazard tape's, the blade's — so
 *  it is fixed at 45° and the plate clips it. A square still fills corner to
 *  corner; a wide plate gets a short steep cancel mark through its centre. */
export function Strike({ color }: { color: string }) {
  const [box, setBox] = React.useState({ w: 0, h: 0 });
  /** Long enough that a 45° line centred on the plate always reaches past
   *  both clipped ends, at any aspect. */
  const length = box.w + box.h;

  return (
    <View
      pointerEvents="none"
      style={[StyleSheet.absoluteFill, { overflow: "hidden" }]}
      onLayout={(e) =>
        setBox({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })
      }
    >
      {length > 0 ? (
        <View
          style={{
            position: "absolute",
            left: (box.w - length) / 2,
            top: box.h / 2,
            width: length,
            height: surface.hairline,
            backgroundColor: color,
            transform: [{ rotate: "-45deg" }],
          }}
        />
      ) : null}
    </View>
  );
}

/** Depth is misregistration, not shadow: a second impression sits one pitch
 *  down and right of the first, both fully opaque. */
export const impression = (n: number): ViewStyle => ({
  marginLeft: n * surface.misregistration,
  marginTop: n === 0 ? 0 : -surface.misregistration,
});

const styles = StyleSheet.create({
  plate: {
    position: "relative",
    borderWidth: surface.hairline,
    borderRadius: surface.radius,
    paddingVertical: surface.platePadY,
    paddingHorizontal: surface.platePadX,
  },
  wide: {
    paddingVertical: surface.actionPadY,
    paddingHorizontal: surface.actionPadX,
  },
  bare: { paddingVertical: 0, paddingHorizontal: 0 },
  screw: {
    position: "absolute",
    width: surface.screw,
    height: surface.screw,
  },
});
