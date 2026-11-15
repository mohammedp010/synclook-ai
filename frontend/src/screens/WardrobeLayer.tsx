/** `"THE WARDROBE"` — Plan v2 Phase 9.
 *
 *  JOB: be the legend for the `"YOURS"` mark. Every outfit the read builds
 *  puts a mark on the pieces the shopper already owns; this layer is where
 *  those pieces live, where new ones are photographed in, and where a wrong
 *  one is struck out.
 *
 *  Phase 8 made it a layer rather than a tab: the closet is *referred to* by
 *  the read, so it opens over the read with the rail still standing, and
 *  closing it puts the reader back exactly where they were. v1 made it a
 *  bottom-tab peer of Home, which asserted the closet is a separate
 *  destination of equal weight — it is not, it is the read's evidence.
 *
 *  AGAINST `wardrobe-desktop-light.jpg` AND `wardrobe-phone-dark.jpg`:
 *  v1 opened with a centred 420pt column, a hanger illustration, the sentence
 *  "Your wardrobe is empty", and a capsule "+ Add item" button — the empty
 *  state was the *entire* composition, with no indication of what a filled
 *  closet looks like or what it is for. This opens with the count and the
 *  action, sets the closet four-up on desktop and two-up on the phone, and
 *  the empty state states what the closet does to a read rather than
 *  apologising for being empty.
 */

import React from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import * as ImagePicker from "expo-image-picker";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { addWardrobeItem, deleteWardrobeItem, listWardrobeItems } from "../api/endpoints";
import { ActionPlate, MaterialSwitch, SecondaryPlate } from "../components/ActionPlate";
import { Code, CodeBlock, Rule } from "../components/Margin";
import { Plate } from "../components/Plate";
import { Rail } from "../components/Rail";
import { Zone } from "../components/Zone";
import { SYNTHETIC, SYNTHETIC_WARDROBE } from "../content/synthetic";
import { useAnalysisScope } from "../navigation/AnalysisScope";
import { ZONE, type RootStackParamList } from "../navigation/routes";
import { useAppStore } from "../store/useAppStore";
import { dye, grid, space, surface } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { bodyMeasure, type } from "../theme/type";
import { cellSize, useFrame, useMeasuredWidth } from "../theme/useFrame";
import type { WardrobeItem } from "../types/api";

/** Dev-only, web-only: `?closet=out` forces the service-unreachable branch so
 *  the reduced state can be looked at on a screen rather than reasoned about.
 *  The same device `devPhase()` uses on the read surface. Compiled out of a
 *  release build and never reachable on a device. */
function devClosetOut(): boolean {
  if (!__DEV__ || typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("closet") === "out";
}

type Props = NativeStackScreenProps<RootStackParamList, "Wardrobe">;

type Load =
  | { state: "loading" }
  | { state: "ok"; items: WardrobeItem[] }
  | { state: "unreachable"; why: string };

export function WardrobeLayer({ navigation }: Props) {
  const { material: m } = useTheme();
  const frame = useFrame();
  const insets = useSafeAreaInsets();
  const userId = useAppStore((s) => s.userId) ?? "demo-user";
  const history = useAppStore((s) => s.analysisHistory);
  const includeProducts = useAppStore((s) => s.includeProducts);
  const { stages, status, warnings } = useAnalysisScope();

  const [load, setLoad] = React.useState<Load>({ state: "loading" });
  const [busy, setBusy] = React.useState(false);

  const refresh = React.useCallback(async () => {
    try {
      if (devClosetOut()) throw new Error("The wardrobe service did not answer.");
      const items = await listWardrobeItems(userId);
      setLoad({ state: "ok", items });
    } catch (e) {
      setLoad({
        state: "unreachable",
        why: e instanceof Error ? e.message : "The wardrobe service did not answer.",
      });
    }
  }, [userId]);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const add = React.useCallback(async () => {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      quality: 0.85,
    });
    if (res.canceled || !res.assets[0]) return;
    setBusy(true);
    try {
      await addWardrobeItem(res.assets[0].uri, userId, "");
      await refresh();
    } catch (e) {
      setLoad({
        state: "unreachable",
        why: e instanceof Error ? e.message : "The wardrobe service did not answer.",
      });
    } finally {
      setBusy(false);
    }
  }, [refresh, userId]);

  const remove = React.useCallback(
    async (id: string) => {
      setBusy(true);
      try {
        await deleteWardrobeItem(id, userId);
        await refresh();
      } finally {
        setBusy(false);
      }
    },
    [refresh, userId],
  );

  /** When the service cannot be reached there is nothing honest to list, so
   *  the closet shown is the synthetic one — tagged, and under a struck plate
   *  that says the real one could not be read. The alternative, an empty grid,
   *  would be a lie shaped like a fact: "you own nothing". */
  const items = load.state === "ok" ? load.items : SYNTHETIC_WARDROBE;
  const synthetic = load.state !== "ok";

  const plane = frame.width - frame.rail;
  const content = plane - frame.margin * 2;

  /** Desktop splits the plane the way the read surface splits it: the act on
   *  the left, what is on file on the right. Ranged full-bleed the layer was a
   *  1075pt action plate with centred type and two-thirds of the plane empty
   *  under it — seen on screen, and not a composition. The closet drops to
   *  three up in the narrower pane so a plate never wraps its type. */
  const split = frame.isDesktop;
  const actW = split ? Math.round((content - grid.gutter) * 0.32) : undefined;
  const cells = split ? 3 : frame.cells;
  const [gridW, onGridLayout] = useMeasuredWidth();
  const cell = cellSize(gridW ?? content, cells);

  const rules = [
    "WHAT THIS DOES TO A READ:",
    "THE MATCHING STAGE CHECKS EVERY SLOT AGAINST THIS LIST FIRST",
    'A SLOT IT COVERS IS MARKED "YOURS" AND IS NEVER PRICED',
    "A SLOT IT CANNOT COVER GOES TO THE SHOPPING STAGE",
  ];

  const act = (
    <View style={{ width: actW, gap: space.s2 }}>
      <ActionPlate
        label={busy ? '"FILING…"' : '"PHOTOGRAPH A PIECE IN"'}
        note="ONE GARMENT PER PHOTOGRAPH · THE SAME VISION PASS READS IT"
        disabled={busy}
        onPress={add}
      />
      <SecondaryPlate label={`BACK TO ${ZONE.read}`} onPress={() => navigation.goBack()} />
      {/* On desktop the rules stand in the act column, which is what keeps it
          a column rather than a stub. On the phone they stay at the foot,
          under the closet they describe. */}
      {split ? <CodeBlock lines={rules} style={{ marginTop: space.s2 }} /> : null}
    </View>
  );

  const filed = (
    <View style={{ flex: split ? 1 : undefined }}>
      {load.state === "loading" ? (
        <Plate>
          <ActivityIndicator color={m.ink} />
          <Code style={{ marginTop: space.s1 }}>READING THE CLOSET</Code>
        </Plate>
      ) : null}

      {load.state === "unreachable" ? (
        <Plate heavy style={{ marginBottom: space.s4 }}>
          <Text style={[type.zoneSmall, { color: m.ink }]}>{'"CLOSET NOT READ"'}</Text>
          <Text style={[type.bodySmall, { color: m.ink, marginTop: 4, maxWidth: bodyMeasure }]}>
            {load.why}
          </Text>
          <CodeBlock
            lines={[
              "THE PIECES BELOW ARE THE PROJECT'S OWN FIXTURE, NOT YOUR CLOSET",
              "A READ STILL RUNS WITHOUT THE CLOSET — IT JUST MARKS NOTHING AS YOURS",
            ]}
            style={{ marginTop: space.s2 }}
          />
          <SecondaryPlate
            label='"TRY AGAIN"'
            onPress={() => {
              setLoad({ state: "loading" });
              refresh();
            }}
            style={{ marginTop: space.s2 }}
          />
        </Plate>
      ) : null}

      {load.state === "ok" && items.length === 0 ? <EmptyCloset /> : null}

      {items.length > 0 ? (
        <View
          onLayout={onGridLayout}
          style={{ flexDirection: "row", flexWrap: "wrap", gap: grid.gutter }}
        >
          {gridW === null
            ? null
            : items.map((item) => (
                <ClosetPlate
                  key={item.id}
                  item={item}
                  size={cell}
                  synthetic={synthetic}
                  onRemove={synthetic ? undefined : () => remove(item.id)}
                />
              ))}
        </View>
      ) : null}
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
        name={ZONE.wardrobe}
        state={
          load.state === "loading"
            ? "READING THE CLOSET"
            : load.state === "unreachable"
              ? "NOT READ — SHOWING A SYNTHETIC CLOSET"
              : `${items.length} ${items.length === 1 ? "PIECE" : "PIECES"} ON FILE · CHECKED AGAINST EVERY READ`
        }
        right={
          synthetic ? (
            <Plate heavy>
              <Text style={[type.plateTitle, { color: m.ink }]}>{SYNTHETIC}</Text>
            </Plate>
          ) : null
        }
      />

      {split ? (
        <View style={{ flexDirection: "row", gap: grid.gutter, alignItems: "flex-start" }}>
          {act}
          {filed}
        </View>
      ) : (
        <>
          <View style={{ marginBottom: space.s4 }}>{act}</View>
          {filed}
          <Rule heavy style={{ marginVertical: space.s5 }} />
          <CodeBlock lines={rules} />
        </>
      )}
    </ScrollView>
  );

  if (!frame.isDesktop) return <View style={{ flex: 1, backgroundColor: m.ground }}>{body}</View>;

  return (
    <View style={{ flex: 1, flexDirection: "row", backgroundColor: m.ground }}>
      <Rail
        object={`${items.length} PIECES`}
        objectId={synthetic ? "SYNTHETIC" : userId.toUpperCase()}
        activeZone={ZONE.wardrobe}
        onRead={() => navigation.navigate("Read")}
        onWardrobe={() => {}}
        onPreviousReads={() => navigation.navigate("PreviousReads")}
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

/** One piece, as a plate. The mark reads `"YOURS"` because that is the word
 *  the outfit grid stamps on it — the legend and the thing it explains use one
 *  vocabulary. */
function ClosetPlate({
  item,
  size,
  synthetic,
  onRemove,
}: {
  item: WardrobeItem;
  size: number;
  synthetic: boolean;
  onRemove?: () => void;
}) {
  const { material: m } = useTheme();
  const swatch = dye[item.color?.toLowerCase()] ?? null;

  return (
    <View style={{ width: size }}>
      {/* The square is used the way the outfit plates use it: the mark at the
          head, the piece's identity at the foot. Stacked from the top, a
          four-line piece left the bottom half of a 226pt plate empty — three
          of those in a row across the desktop pane read as a grid of holes. */}
      <Plate style={{ minHeight: size, justifyContent: "space-between" }}>
        {/* The mark alone at the head. The lot number rode beside it and
            collided with it in a 157pt phone cell — `"SYNTHETIC"WD-0112`, no
            space between them — so it moved to the code line at the foot,
            which is where this world keeps lot numbers anyway. */}
        <View style={{ flexDirection: "row" }}>
          <Code full>{synthetic ? SYNTHETIC : '"YOURS"'}</Code>
        </View>

        <View style={{ marginTop: space.s3 }}>
          <Text style={[type.zoneSmall, { color: m.ink }]} numberOfLines={2}>
            {item.clothing_type.replace(/_/g, " ").toUpperCase()}
          </Text>

          <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 6 }}>
            {swatch ? (
              <View
                style={{
                  width: 13,
                  height: 13,
                  backgroundColor: swatch,
                  borderWidth: surface.hairline,
                  borderColor: m.stroke,
                }}
              />
            ) : null}
            <Text style={[type.plateValue, { color: m.ink }]} numberOfLines={1}>
              {item.color.toUpperCase()}
            </Text>
          </View>

          <Code style={{ marginTop: 6 }}>
            {`${item.pattern} · ${item.style} · ${item.id}`.replace(/_/g, " ").toUpperCase()}
          </Code>

          {item.label ? (
            <Text style={[type.bodySmall, { color: m.ink, marginTop: 6 }]} numberOfLines={2}>
              {item.label}
            </Text>
          ) : null}
        </View>
      </Plate>

      {onRemove ? (
        <Pressable
          onPress={onRemove}
          accessibilityRole="button"
          accessibilityLabel={`Strike ${item.label || item.clothing_type} from the wardrobe`}
          style={({ pressed }) => ({
            minHeight: 44,
            justifyContent: "center",
            opacity: pressed ? 0.6 : 1,
          })}
        >
          <Code full>{'"STRIKE IT"'}</Code>
        </Pressable>
      ) : null}
    </View>
  );
}

/** The empty closet says what the closet *does*, because the reader has
 *  arrived here to find that out. v1's version said "Your wardrobe is empty"
 *  under a hanger drawing, which is the one thing the reader could already
 *  see. */
function EmptyCloset() {
  const { material: m } = useTheme();
  return (
    <Plate heavy>
      <Text style={[type.zoneSmall, { color: m.ink }]}>{'"NOTHING ON FILE"'}</Text>
      <Text style={[type.body, { color: m.ink, marginTop: 6, maxWidth: bodyMeasure }]}>
        Every read still works. It just has nothing of yours to mark, so every
        slot in the outfit goes to the shopping stage and gets priced.
      </Text>
      <CodeBlock
        lines={[
          "PHOTOGRAPH THE PIECES YOU WEAR MOST FIRST",
          "FOUR OR FIVE IS ENOUGH TO CHANGE WHAT A READ RETURNS",
        ]}
        style={{ marginTop: space.s2 }}
      />
    </Plate>
  );
}
