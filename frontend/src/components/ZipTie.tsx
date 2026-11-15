/** The zip-tie tag — Plan v2 Phase 9.
 *
 *  OWN-WORLD: "Zip-tie tags hang off anything the app did not make." That is
 *  the rule, and it is what makes the safety orange mean something: a piece
 *  the shopper already owns carries no tag at all, only the word `"YOURS"`.
 *  Orange is therefore never decoration and never emphasis — it is the field a
 *  price is printed on, at page scale.
 *
 *  The strap is drawn: a hairline stem out of the plate above with a square
 *  tie head, then the orange field under it. Near-black prints on the field in
 *  both materials (6.33:1); orange is never ink on cotton (3.13:1).
 */

import React from "react";
import { Text, View } from "react-native";

import { surface, tag } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { type } from "../theme/type";
import { Screws } from "./Plate";

export function ZipTie({
  /** The ₹ figure, verbatim from `ProductLink.price`. */
  price,
  /** `ProductLink.source` — the retailer that actually listed it. */
  source,
  /** `ProductLink.title`, printed in the margin under the field. */
  title,
  /** Retrieval facts from `match_evidence` / `match_reason`. */
  evidence,
  width,
}: {
  price: string;
  source: string;
  title?: string;
  evidence?: string[];
  width?: number;
}) {
  const { material: m } = useTheme();

  return (
    <View style={{ width, alignItems: "flex-start" }}>
      {/* The strap, out of the plate above. */}
      <View style={{ flexDirection: "row", alignItems: "flex-start", marginLeft: 11 }}>
        <View style={{ width: surface.hairline, height: 11, backgroundColor: m.strokeHeavy }} />
        <View
          style={{
            width: 7,
            height: 5,
            marginLeft: -3,
            marginTop: 6,
            backgroundColor: m.strokeHeavy,
          }}
        />
      </View>

      <View
        style={{
          alignSelf: "stretch",
          backgroundColor: tag.field,
          paddingVertical: 7,
          paddingHorizontal: 9,
          position: "relative",
        }}
      >
        <Screws color={tag.ink} />
        <Text style={[type.plateTitle, { color: tag.ink }]}>{price}</Text>
        <Text style={[type.code, { color: tag.ink, marginTop: 2 }]} numberOfLines={1}>
          {source.toUpperCase()}
        </Text>
      </View>

      {title ? (
        <Text
          style={[type.code, { color: m.ink, opacity: 0.7, marginTop: 4 }]}
          numberOfLines={2}
        >
          {title.toUpperCase()}
        </Text>
      ) : null}
      {evidence?.slice(0, 2).map((line) => (
        <Text
          key={line}
          style={[type.code, { color: m.ink, opacity: 0.7, marginTop: 2 }]}
          numberOfLines={1}
        >
          {line.toUpperCase()}
        </Text>
      ))}
    </View>
  );
}
