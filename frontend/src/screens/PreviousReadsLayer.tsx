/** `"PREVIOUS READS"` — Plan v2 Phase 9.
 *
 *  JOB: be the file. The store already keeps the last twenty results; until
 *  now nothing in the app could see them, so a shopper who read three garments
 *  in a shop had two of them silently discarded. This is the shelf they sit
 *  on.
 *
 *  WHY A LAYER AND NOT A RAIL LIST (the Phase 8 open question, settled here):
 *  twenty reads, each with five words and an outfit, need the plane. The rail
 *  carries the quoted name and a live count — enough to know the file exists
 *  and how deep it is — and opening it gives the file the whole plane. A rail
 *  list would have to truncate to three or four entries and would put the
 *  file's *contents* in the apparatus, which is exactly the "navigation as a
 *  menu of destinations" reading Phase 8 refused.
 *
 *  WHERE THE MISREGISTRATION GOES: the direction contract spends depth on a
 *  5pt offset impression, never a shadow. A stack of reads is the one place in
 *  the build where that is literally what is being drawn — each impression
 *  steps 5pt right of the one above, so the file reads as a stack of printed
 *  sheets rather than a list of rows.
 *
 *  HONESTY: `StreamAnalysisResult` carries no timestamp, so no impression here
 *  is dated. They are ordered — `"MOST RECENT"`, then how many reads back —
 *  and the margin says the file is this session's. Inventing dates for a
 *  stack that never recorded any would be exactly the kind of plausible
 *  fiction the craft floor refuses.
 */

import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { MaterialSwitch, SecondaryPlate } from "../components/ActionPlate";
import { Hazard } from "../components/Hazard";
import { Code, CodeBlock } from "../components/Margin";
import { impression, Plate } from "../components/Plate";
import { Rail } from "../components/Rail";
import { WordStack, type WordRow } from "../components/Stencil";
import { Zone } from "../components/Zone";
import { useAnalysisScope } from "../navigation/AnalysisScope";
import { ZONE, type RootStackParamList } from "../navigation/routes";
import { useAppStore } from "../store/useAppStore";
import { dye, grid, space, surface } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { bodyMeasure, type } from "../theme/type";
import { useFrame } from "../theme/useFrame";
import type { StreamAnalysisResult } from "../types/api";

type Props = NativeStackScreenProps<RootStackParamList, "PreviousReads">;

export function PreviousReadsLayer({ navigation }: Props) {
  const { material: m } = useTheme();
  const frame = useFrame();
  const insets = useSafeAreaInsets();
  const history = useAppStore((s) => s.analysisHistory);
  const includeProducts = useAppStore((s) => s.includeProducts);
  const { stages, status, warnings } = useAnalysisScope();
  const [open, setOpen] = React.useState<string | null>(null);

  /** Same split as the wardrobe layer and the read surface: the act on the
   *  left, the file on the right. A stack of impressions ranged across the
   *  whole 1075pt plane made every sheet a banner and left the plane empty
   *  below the first one. */
  const split = frame.isDesktop;
  const content = frame.width - frame.rail - frame.margin * 2;
  const actW = split ? Math.round((content - grid.gutter) * 0.32) : undefined;

  const rules = [
    "THE FILE HOLDS TWENTY · THE TWENTY-FIRST READ PUSHES THE OLDEST OFF",
    "IT IS HELD IN MEMORY FOR THIS SESSION AND IS NOT SENT ANYWHERE",
    "CLOSING THE APP CLEARS IT",
    "NO IMPRESSION IS DATED · THE RESULT CARRIES NO TIME",
  ];

  const act = (
    <View style={{ width: actW, gap: space.s2 }}>
      <SecondaryPlate label={`BACK TO ${ZONE.read}`} onPress={() => navigation.goBack()} />
      {split ? <CodeBlock lines={rules} style={{ marginTop: space.s2 }} /> : null}
    </View>
  );

  const file = (
    <View style={{ flex: split ? 1 : undefined }}>
      {history.length === 0 ? (
        <Plate heavy>
          <Text style={[type.zoneSmall, { color: m.ink }]}>{'"THE FILE IS EMPTY"'}</Text>
          <Text style={[type.body, { color: m.ink, marginTop: 6, maxWidth: bodyMeasure }]}>
            Every garment you read this session gets filed here: the five words
            the machine read, and the outfit it built around them.
          </Text>
          <CodeBlock
            lines={[
              "PHOTOGRAPH A GARMENT ON THE READ TO FILE THE FIRST ONE",
              "THE FILE FILLS AS YOU WORK · NOTHING HAS TO BE SAVED",
            ]}
            style={{ marginTop: space.s2 }}
          />
        </Plate>
      ) : null}

      {history.map((entry, i) => (
        <Impression
          key={entry.request_id ?? `read-${i}`}
          entry={entry}
          index={i}
          open={open === (entry.request_id ?? `read-${i}`)}
          onToggle={() =>
            setOpen((cur) => {
              const id = entry.request_id ?? `read-${i}`;
              return cur === id ? null : id;
            })
          }
        />
      ))}
    </View>
  );

  const body = (
    <ScrollView
      style={{ flex: 1, backgroundColor: m.ground }}
      contentContainerStyle={{
        paddingHorizontal: frame.margin,
        paddingTop: insets.top + space.s4,
        paddingBottom: space.s6 + insets.bottom,
      }}
    >
      {!frame.isDesktop ? (
        <View style={{ marginBottom: space.s4 }}>
          <View style={{ flexDirection: "row", alignItems: "flex-start", gap: space.s2 }}>
            <Text style={[type.zone, { color: m.ink, flex: 1 }]}>SYNCLOOK</Text>
            <MaterialSwitch />
          </View>
          <View
            style={{ height: surface.rule, backgroundColor: m.strokeHeavy, marginTop: space.s2 }}
          />
        </View>
      ) : null}

      <Zone
        name={ZONE.previousReads}
        state={
          history.length === 0
            ? "NOTHING FILED THIS SESSION"
            : `${history.length} OF 20 · THIS SESSION ONLY · NOT DATED`
        }
      />

      {split ? (
        <View style={{ flexDirection: "row", gap: grid.gutter, alignItems: "flex-start" }}>
          {act}
          {file}
        </View>
      ) : (
        <>
          <View style={{ marginBottom: space.s4 }}>{act}</View>
          {file}
          <CodeBlock lines={rules} style={{ marginTop: space.s5 }} />
        </>
      )}
    </ScrollView>
  );

  if (!frame.isDesktop) return <View style={{ flex: 1, backgroundColor: m.ground }}>{body}</View>;

  return (
    <View style={{ flex: 1, flexDirection: "row", backgroundColor: m.ground }}>
      <Rail
        object={`${history.length} READS`}
        objectId="THIS SESSION"
        activeZone={ZONE.previousReads}
        onRead={() => navigation.navigate("Read")}
        onWardrobe={() => navigation.navigate("Wardrobe")}
        onPreviousReads={() => {}}
        previousCount={history.length}
        stages={stages}
        hasRun={status !== "idle"}
        includeProducts={includeProducts}
        warnings={warnings}
      />
      <View style={{ flex: 1 }}>{body}</View>
    </View>
  );
}

/** One sheet in the stack. Closed it prints the garment word, the dye chip,
 *  the outfit's size and whether the verifier flagged anything — the four
 *  facts that tell one read from another. Open it prints the five words and
 *  the pieces.
 *
 *  It does not offer to reopen the read on the main surface. The stream cannot
 *  be resumed and the result is not re-derivable from what is stored, so a
 *  "restore" action would be a button that lies. */
function Impression({
  entry,
  index,
  open,
  onToggle,
}: {
  entry: StreamAnalysisResult;
  index: number;
  open: boolean;
  onToggle: () => void;
}) {
  const { material: m } = useTheme();
  const attrs = entry.detected_attributes;
  const rec = entry.recommendations?.[0] ?? null;
  const flagged = (entry.errors?.length ?? 0) > 0;
  const swatch = attrs ? (dye[attrs.primary_color?.toLowerCase()] ?? null) : null;

  const rows: WordRow[] = attrs
    ? [
        { head: "TYPE", word: attrs.clothing_type.toUpperCase(), confidence: attrs.confidence },
        {
          head: "COLOUR",
          word: attrs.primary_color.toUpperCase(),
          confidence: attrs.color_confidence,
        },
        { head: "COLOUR", word: attrs.secondary_color?.toUpperCase() ?? null, tied: true },
        { head: "PATTERN", word: attrs.pattern.toUpperCase(), confidence: attrs.pattern_confidence },
        { head: "STYLE", word: attrs.style.toUpperCase(), confidence: attrs.style_confidence },
      ]
    : [];

  return (
    <View style={[impression(Math.min(index, 4)), { marginBottom: space.s2 }]}>
      <Pressable
        onPress={onToggle}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={`${attrs?.clothing_type ?? "Read"}, ${
          index === 0 ? "most recent" : `${index} reads back`
        }`}
        style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
      >
        <Plate heavy={open}>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <Code full>{index === 0 ? "MOST RECENT" : `${index} READS BACK`}</Code>
            <Code>{entry.request_id?.toUpperCase() ?? "NO ID"}</Code>
          </View>

          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: space.s2,
              marginTop: space.s1,
            }}
          >
            {swatch ? (
              <View
                style={{
                  width: 15,
                  height: 15,
                  backgroundColor: swatch,
                  borderWidth: surface.hairline,
                  borderColor: m.stroke,
                }}
              />
            ) : null}
            <Text style={[type.zoneSmall, { color: m.ink, flex: 1 }]} numberOfLines={1}>
              {attrs
                ? `${attrs.primary_color} ${attrs.clothing_type}`.replace(/_/g, " ").toUpperCase()
                : "NOT READ"}
            </Text>
            <Code>{open ? '"OPEN"' : '"FILED"'}</Code>
          </View>

          <Code style={{ marginTop: 6 }}>
            {[
              rec ? `${rec.items.length} PIECES` : "NO OUTFIT",
              rec ? `${rec.items.filter((i) => i.owned).length} YOURS` : null,
              flagged ? `${entry.errors?.length} FLAGGED` : "NOTHING FLAGGED",
            ]
              .filter(Boolean)
              .join(" · ")}
          </Code>

          {flagged ? <Hazard height={9} /> : null}

          {open ? (
            <View style={{ marginTop: space.s3 }}>
              {rows.length ? <WordStack rows={rows} size={type.stencilPhone} /> : null}

              {rec ? (
                <View style={{ marginTop: space.s3 }}>
                  {rec.items.map((item, k) => (
                    <View
                      key={`${item.item_type}-${k}`}
                      style={{ flexDirection: "row", gap: space.s2, marginTop: 4 }}
                    >
                      <Code full>{item.owned ? '"YOURS"' : '"TO BUY"'}</Code>
                      <Text
                        style={[type.plateValue, { color: m.ink, flex: 1 }]}
                        numberOfLines={1}
                      >
                        {`${item.color} ${item.item_type}`.replace(/_/g, " ").toUpperCase()}
                      </Text>
                      {!item.owned && item.products?.[0] ? (
                        <Code full>{item.products[0].price}</Code>
                      ) : null}
                    </View>
                  ))}
                </View>
              ) : null}

              {entry.errors?.length ? (
                <CodeBlock lines={entry.errors} style={{ marginTop: space.s2 }} />
              ) : null}
            </View>
          ) : null}
        </Plate>
      </Pressable>
    </View>
  );
}
