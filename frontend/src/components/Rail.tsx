/** The desktop rail — Plan v2 Phase 9.
 *
 *  FIRST VIEWPORT — DESKTOP: "A fixed left rail … holding the mark, an
 *  `OBJECT / ID / ZONE` identity plate, the quoted destinations as a vertical
 *  list, and a live `SYSTEM STATUS` plate at the bottom naming which stages
 *  are running and which degraded."
 *
 *  It is printed in the counter material to the main plane, which is Phase 8's
 *  reading of the contract's "cotton-white" (see `CounterMaterial`). The rail
 *  is apparatus; the plane is the work.
 *
 *  The mark is set unquoted. Quotation marks in this world are load-bearing —
 *  they belong to the machine's literal words and to the zone names — and
 *  spending them on the product's own name is exactly the slide into costume
 *  the HONEST RISK block warns about.
 *
 *  v1 had no rail, no desktop composition of any kind: a `maxWidth` cap and
 *  two-thirds of a 1470px viewport left empty.
 */

import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import type { StageState } from "../hooks/useAnalysis";
import { ZONE } from "../navigation/routes";
import { dim, grid, space, surface } from "../theme/material";
import { CounterMaterial, useTheme } from "../theme/ThemeProvider";
import { type } from "../theme/type";
import { Code, CodeBlock } from "./Margin";
import { MaterialSwitch } from "./ActionPlate";
import { SystemStatusPlate } from "./SystemStatusPlate";

export interface RailProps {
  /** The object currently on the surface: its type word and its request id. */
  object: string;
  objectId: string;
  /** The zone the reader is in — one of `ZONE`'s quoted names. */
  activeZone: string;
  onWardrobe: () => void;
  onPreviousReads: () => void;
  onRead: () => void;
  previousCount: number;
  stages: StageState[];
  hasRun: boolean;
  includeProducts: boolean;
  warnings: string[];
}

export function Rail(props: RailProps) {
  return (
    <CounterMaterial>
      <RailBody {...props} />
    </CounterMaterial>
  );
}

function RailBody({
  object,
  objectId,
  activeZone,
  onWardrobe,
  onPreviousReads,
  onRead,
  previousCount,
  stages,
  hasRun,
  includeProducts,
  warnings,
}: RailProps) {
  const { material: m } = useTheme();

  const destinations: Array<[string, string, () => void]> = [
    [ZONE.read, "THE ACT", onRead],
    [ZONE.wardrobe, "WHAT YOU OWN", onWardrobe],
    [ZONE.previousReads, `${previousCount} ON FILE`, onPreviousReads],
  ];

  return (
    <View
      style={{
        width: grid.rail,
        backgroundColor: m.ground,
        borderRightWidth: surface.rule,
        borderRightColor: m.strokeHeavy,
      }}
    >
      <ScrollView contentContainerStyle={{ padding: space.s4, paddingBottom: space.s5 }}>
        <Text style={[type.zone, { color: m.ink }]}>SYNCLOOK</Text>
        <CodeBlock
          lines={["ONE GARMENT IN,", "A WHOLE OUTFIT OUT", "INDIA · ₹"]}
          style={{ marginTop: space.s1 }}
        />

        <View style={{ height: space.s4 }} />

        {/* The identity plate. Real values: the word the vision pass returned
            for the object on the surface, and the request id the stream
            issued for it. */}
        <View
          style={{
            borderWidth: surface.hairline,
            borderColor: m.stroke,
            padding: space.s2,
          }}
        >
          <Code>OBJECT</Code>
          <Text style={[type.plateValue, { color: m.ink }]} numberOfLines={1}>
            {object}
          </Text>
          <Code style={{ marginTop: space.s1 }}>ID</Code>
          <Text style={[type.plateValue, { color: m.ink }]} numberOfLines={1}>
            {objectId}
          </Text>
          <Code style={{ marginTop: space.s1 }}>ZONE</Code>
          <Text style={[type.plateValue, { color: m.ink }]} numberOfLines={1}>
            {activeZone}
          </Text>
        </View>

        <View style={{ height: space.s4 }} />

        {destinations.map(([name, note, go]) => {
          const on = name === activeZone;
          return (
            <Pressable
              key={name}
              onPress={go}
              accessibilityRole="link"
              accessibilityState={{ selected: on }}
              accessibilityLabel={`${name}, ${note}`}
              style={({ pressed }) => ({
                marginBottom: space.s2,
                opacity: pressed ? 0.6 : 1,
                minHeight: 44,
                justifyContent: "center",
              })}
            >
              <Text style={[type.zoneSmall, { color: m.ink, opacity: on ? 1 : dim }]}>
                {name}
              </Text>
              {/* The zone you are in carries the same 2pt rule every zone head
                  on the plane carries. Not a coloured left border — that is
                  the callout device the craft floor refuses, and this world
                  already owns a mark for "this is a zone". */}
              {on ? (
                <View style={{ height: surface.rule, backgroundColor: m.strokeHeavy, marginTop: 2 }} />
              ) : null}
              <Code>{note}</Code>
            </Pressable>
          );
        })}

        <View style={{ height: space.s4 }} />
        <MaterialSwitch />

        <View style={{ height: space.s4 }} />
        <SystemStatusPlate
          stages={stages}
          hasRun={hasRun}
          includeProducts={includeProducts}
          warnings={warnings}
          stacked
        />
      </ScrollView>
    </View>
  );
}
