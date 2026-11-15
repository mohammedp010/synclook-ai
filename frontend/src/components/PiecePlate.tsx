/** One piece of the outfit — Plan v2 Phase 9.
 *
 *  The product's second differentiator is that the wardrobe comes first:
 *  owned items are matched and marked before the shopping stage runs, and
 *  shopping only covers the slots the closet could not fill. So the mark is
 *  the first thing on the plate, and the tag is what is missing from an owned
 *  piece rather than what is added to a bought one.
 *
 *  The cell is square by rule; the piece's commerce hangs *below* it as a
 *  zip-tie tag, which is the composition the direction contract describes
 *  ("plates set square across a strict grid, four up, tags hanging"). A
 *  square that had to hold a title, a price, a source and three retrieval
 *  facts would stop being a square.
 *
 *  There is no product thumbnail. `ProductLink.thumbnail` exists, but a grid
 *  of remote retailer images is the card kit this world replaced, and the
 *  garment's own dye — content, quarantined in `material.ts` — is the honest
 *  colour signal. A chip is never colour alone: hairline plus the name.
 */

import React from "react";
import { Linking, Pressable, Text, View } from "react-native";

import { dim, dye, space, surface } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { type } from "../theme/type";
import type { RecommendationItem } from "../types/api";
import { Code } from "./Margin";
import { Plate } from "./Plate";
import { ZipTie } from "./ZipTie";

export type PieceMark = "YOURS" | "TO BUY" | "READ" | "OPEN";

export function PiecePlate({
  item,
  size,
  /** The garment the shopper photographed, printed into the grid as the piece
   *  the outfit was built around. */
  isRead,
  /** Flagged by the verifier — the caller draws the hazard band under the row. */
  flagged,
}: {
  item: RecommendationItem;
  size: number;
  isRead?: boolean;
  flagged?: boolean;
}) {
  const { material: m } = useTheme();
  const product = item.products?.[0];
  const owned = !!item.owned;
  const mark: PieceMark = isRead ? "READ" : owned ? "YOURS" : product ? "TO BUY" : "OPEN";
  const swatch = dye[item.color?.toLowerCase()] ?? null;

  return (
    <View style={{ width: size }}>
      <Plate
        heavy={isRead}
        bare
        style={{ height: size, justifyContent: "space-between", padding: space.s2 }}
      >
        {/* The mark, first. */}
        <View style={{ alignSelf: "flex-start", flexDirection: "row" }}>
          <View
            style={{
              borderWidth: surface.hairline,
              borderColor: m.strokeHeavy,
              paddingVertical: 3,
              paddingHorizontal: 5,
            }}
          >
            <Text style={[type.plateTitle, { color: m.ink }]}>{`"${mark}"`}</Text>
          </View>
        </View>

        <View>
          <Text
            style={[type.zoneSmall, { color: m.ink }]}
            numberOfLines={2}
            adjustsFontSizeToFit={false}
          >
            {`"${item.item_type.replace(/_/g, " ").toUpperCase()}"`}
          </Text>

          {/* Dye: chip plus name, never colour alone. `other` is null in the
              map, so an unnamed colour prints struck rather than guessed. */}
          <View style={{ flexDirection: "row", alignItems: "center", gap: 5, marginTop: 4 }}>
            <View
              style={{
                width: 13,
                height: 13,
                backgroundColor: swatch ?? "transparent",
                borderWidth: surface.hairline,
                borderColor: m.stroke,
              }}
            />
            <Code numberOfLines={1} style={{ flex: 1 }}>
              {`${item.color.toUpperCase()}${
                item.style ? ` · ${item.style.replace(/_/g, " ").toUpperCase()}` : ""
              }`}
            </Code>
          </View>
        </View>
      </Plate>

      {/* What hangs off it. */}
      {product && !owned ? (
        <Pressable
          onPress={() => product.link && Linking.openURL(product.link).catch(() => {})}
          accessibilityRole="link"
          accessibilityLabel={`${product.title}, ${product.price} at ${product.source}`}
        >
          <ZipTie
            price={product.price}
            source={product.source}
            title={product.title}
            evidence={product.match_evidence ?? (product.match_reason ? [product.match_reason] : [])}
          />
        </Pressable>
      ) : (
        <View style={{ marginTop: space.s1 }}>
          <Code full>
            {/* The read garment is checked first: it is neither owned nor for
                sale, and printing FROM YOUR WARDROBE under the photograph the
                shopper just took was wrong on screen. */}
            {isRead
              ? "THE GARMENT YOU PHOTOGRAPHED"
              : owned
                ? `FROM YOUR WARDROBE${
                    item.wardrobe_item_id ? ` · ${item.wardrobe_item_id.toUpperCase()}` : ""
                  }`
                : "NO LISTING COVERED THIS SLOT"}
          </Code>
        </View>
      )}

      {item.reason ? (
        <Text
          style={[type.bodySmall, { color: m.ink, opacity: dim, marginTop: space.s1 }]}
          numberOfLines={4}
        >
          {item.reason}
        </Text>
      ) : null}

      {flagged ? (
        <View style={{ marginTop: space.s1 }}>
          <Code full>FLAGGED BY THE VERIFIER · SEE THE BAND BELOW</Code>
        </View>
      ) : null}
    </View>
  );
}

/** A slot the closet could not fill and shopping did not cover. A real
 *  reduced state: the outfit is incomplete and says so, in a plate, rather
 *  than quietly showing three pieces where there should be four. */
export function OpenSlot({ label, size }: { label: string; size: number }) {
  const { material: m } = useTheme();
  return (
    <View style={{ width: size }}>
      {/* `Plate` fastens its own screws — a second set was being drawn here at
          the same insets in the same ink, one impression on top of the other. */}
      <Plate struck bare style={{ height: size, justifyContent: "flex-end", padding: space.s2 }}>
        <Text style={[type.zoneSmall, { color: m.ink, opacity: dim }]}>{`"${label}"`}</Text>
      </Plate>
      <Code style={{ marginTop: space.s1 }}>SLOT OPEN · NOTHING PRICED UNDER YOUR CAP</Code>
    </View>
  );
}
