/** `Read` — the whole act, Plan v2 Phase 9.
 *
 *  JOB (surface brief, Flow architecture): hold one garment photograph, show
 *  the machine's five quoted words as it reads them, and stand the outfit up
 *  beside them with the shopper's own pieces marked before anything is billed.
 *
 *  Phase 8 collapsed v1's Landing → Home → Camera → Analysis → Results into
 *  this one surface with internal phases, because the signature interaction
 *  requires it: the reading stencils each attribute onto the user's own
 *  photograph as its stream event arrives, and that is not implementable
 *  across a route boundary. `useAnalysis` already owns the state machine; this
 *  screen reads it through `readPhase()` and never keeps a second copy.
 *
 *  WHAT CHANGED IN THE READING ORDER, against `home-*.jpg` and `landing-*.jpg`
 *  opened side by side:
 *
 *  - v1 opened with a sentence about the product ("Find your perfect outfit"),
 *    a subhead, three stacked capsule buttons and a vector illustration in the
 *    right column; the instrument — the intent field, the shopping intent, the
 *    upload — was below the fold on both frames. This opens with the
 *    instrument at the top of the first zone and the machine's five words at
 *    display scale immediately under it. Nothing on this surface describes the
 *    product.
 *  - v1's desktop was a `maxWidth: 420` column centred in a 1470px viewport.
 *    This is a fixed rail plus a split plane, with the outfit four up.
 *  - v1 announced the AI with a badge pill and a lightning bolt. The evidence
 *    here is the `"SYSTEM STATUS"` plate naming which stages ran.
 *
 *  Phase 10 authors the `reading` moment — the stream landing word by word on
 *  the photograph. Phase 11 orchestrates the motion. This phase stands the
 *  surfaces up and leaves both alone: content is printed, nothing tweens.
 */

import React from "react";
import {
  Platform,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import * as ImagePicker from "expo-image-picker";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { submitFeedback } from "../api/endpoints";
import { ActionPlate, MaterialSwitch, SecondaryPlate } from "../components/ActionPlate";
import { GarmentPort } from "../components/GarmentPort";
import { Hazard } from "../components/Hazard";
import { IntentField, IntentStamp } from "../components/IntentField";
import { Code, CodeBlock, Rule } from "../components/Margin";
import { OpenSlot, PiecePlate } from "../components/PiecePlate";
import { Plate } from "../components/Plate";
import { Rail } from "../components/Rail";
import { Selector, WordSwitch } from "../components/StateSwitch";
import { WordStack, type WordRow } from "../components/Stencil";
import { SystemStatusPlate } from "../components/SystemStatusPlate";
import { Zone } from "../components/Zone";
import {
  SYNTHETIC,
  SYNTHETIC_INTENT,
  SYNTHETIC_READ,
} from "../content/synthetic";
import { useAnalysisScope } from "../navigation/AnalysisScope";
import {
  readPhase,
  STAGE_WORD,
  ZONE,
  type ReadPhase,
  type RootStackParamList,
} from "../navigation/routes";
import { useAppStore } from "../store/useAppStore";
import { dim, grid, space, surface } from "../theme/material";
import { useTheme } from "../theme/ThemeProvider";
import { bodyMeasure, type } from "../theme/type";
import { cellSize, useFrame, useMeasuredWidth } from "../theme/useFrame";
import type {
  ClothingAttributes,
  RecommendationItem,
  ShoppingIntent,
  StreamAnalysisResult,
} from "../types/api";

type Props = NativeStackScreenProps<RootStackParamList, "Read">;

/** A zone name Phase 8 did not need to name, because it exists only while the
 *  surface is empty: the worked read that answers the cold open. */
const WORKED = '"A WORKED READ"';

const SHOPPING_INTENTS: ReadonlyArray<readonly [ShoppingIntent, string]> = [
  ["menswear", "MENSWEAR"],
  ["womenswear", "WOMENSWEAR"],
  ["unisex", "UNISEX"],
  ["all", "ALL"],
];

/** THE FIVE SLOTS, AND THE FOUR HEADS THAT MEASURE THEM.
 *
 *  `ClothingAttributes` carries `confidence`, `color_confidence`,
 *  `pattern_confidence` and `style_confidence` — four. The fifth word,
 *  `secondary_color`, has no head of its own; it shares the colour head, so it
 *  is tied to the row above rather than given a figure that does not exist.
 *  `arrived` is how many stream events have landed, which is what lets Phase
 *  10 print them one at a time without this function changing. */
function wordRows(attrs: ClothingAttributes | null, arrived = 5): WordRow[] {
  const slots: WordRow[] = [
    { head: "TYPE", word: attrs?.clothing_type ?? null, confidence: attrs?.confidence },
    { head: "COLOUR", word: attrs?.primary_color ?? null, confidence: attrs?.color_confidence },
    { head: "COLOUR", word: attrs?.secondary_color ?? null, tied: true },
    { head: "PATTERN", word: attrs?.pattern ?? null, confidence: attrs?.pattern_confidence },
    { head: "STYLE", word: attrs?.style ?? null, confidence: attrs?.style_confidence },
  ];
  return slots.map((row, i) => ({
    ...row,
    word: i < arrived ? (row.word ? row.word.replace(/_/g, " ").toUpperCase() : null) : null,
    waiting: i >= arrived,
  }));
}

/** The photographed garment, printed into the outfit grid as the piece the
 *  outfit was built around. It is not in `recommendations[].items` — the
 *  backend describes what to add — but leaving it out makes the grid read as
 *  an outfit that does not include the thing the shopper is holding. */
function readGarment(attrs: ClothingAttributes): RecommendationItem {
  return {
    item_type: attrs.clothing_type,
    color: attrs.primary_color,
    style: attrs.style,
    reason: attrs.description_relevant ? attrs.description : "",
    /** Not owned and not for sale. `PiecePlate` marks it `"READ"` off
     *  `isRead`, which is the only mark that fits it. */
    owned: false,
    products: [],
  };
}

/** `__DEV__` capture harness. Phases that need a live backend, a real stream
 *  or a picked photograph cannot be reached from an automated browser, so the
 *  design review reaches them with `?phase=`. It is dev-only, it never
 *  fabricates a result — it composes the same synthetic read every other
 *  reduced state uses — and the margin says so on screen. */
function devPhase(): ReadPhase | null {
  if (!__DEV__ || Platform.OS !== "web") return null;
  const search = (globalThis as { location?: { search?: string } }).location?.search;
  const value = search ? new URLSearchParams(search).get("phase") : null;
  return value === "held" || value === "reading" || value === "read" || value === "struck"
    ? value
    : null;
}

export function ReadScreen({ navigation, route }: Props) {
  const { material: m } = useTheme();
  const frame = useFrame();
  const insets = useSafeAreaInsets();

  const currentImage = useAppStore((s) => s.currentImage);
  const setCurrentImage = useAppStore((s) => s.setCurrentImage);
  const userIntent = useAppStore((s) => s.userIntent);
  const setUserIntent = useAppStore((s) => s.setUserIntent);
  const shoppingIntent = useAppStore((s) => s.shoppingIntent);
  const setShoppingIntent = useAppStore((s) => s.setShoppingIntent);
  const includeProducts = useAppStore((s) => s.includeProducts);
  const setIncludeProducts = useAppStore((s) => s.setIncludeProducts);
  const history = useAppStore((s) => s.analysisHistory);
  const userId = useAppStore((s) => s.userId);
  const feedbackGiven = useAppStore((s) => s.feedbackGiven);
  const setFeedback = useAppStore((s) => s.setFeedback);

  const { status, stages, result, error, warnings, elapsed, analyze, reset } = useAnalysisScope();

  /** `Analysis: { imageUri }` survives as `Read: { imageUri? }`, same meaning. */
  React.useEffect(() => {
    const handed = route.params?.imageUri;
    if (handed && handed !== currentImage) setCurrentImage(handed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.params?.imageUri]);

  const override = devPhase();
  const phase: ReadPhase = override ?? readPhase(status, !!currentImage);
  /** The worked read stands in the outfit pane until a real one replaces it —
   *  through `empty` and `held` both, so the reader holding a photograph can
   *  see exactly what pressing the orange plate will produce. It is tagged
   *  `"SYNTHETIC"` in its own zone head every time it is on screen, and it is
   *  gone the moment a real result exists. `struck` drops it: a failure owns
   *  the plane. */
  const synthetic = !result && (phase === "empty" || phase === "held");
  /** Under the capture harness the synthetic read stands in for the real one
   *  so `read` can be composed without a backend; it is not *also* printed as
   *  the worked read, or the same five words would appear twice on one plane.
   *  The zone head says CAPTURE HARNESS wherever it is standing in.
   *
   *  Only `read` gets the stand-in. `?phase=struck` was handing the fixture to
   *  the outfit pane too, so the capture showed a built outfit beside a plate
   *  saying the garment could not be read — a composition the shipped code
   *  never produces, since a real `struck` has no result at all. The harness
   *  may compose a state; it may not compose a state the app cannot reach. */
  const shown: StreamAnalysisResult | null =
    result ?? (synthetic || override === "read" ? SYNTHETIC_READ : null);

  const pick = React.useCallback(
    async (from: "library" | "camera") => {
      const opts = { mediaTypes: ["images" as const], quality: 0.85 };
      const res =
        from === "camera"
          ? await ImagePicker.launchCameraAsync(opts)
          : await ImagePicker.launchImageLibraryAsync(opts);
      if (!res.canceled && res.assets[0]) {
        reset();
        setCurrentImage(res.assets[0].uri);
      }
    },
    [reset, setCurrentImage],
  );

  const body = (
    <Plane
      phase={phase}
      synthetic={synthetic}
      shown={shown}
      frameIsDesktop={frame.isDesktop}
      width={frame.width}
      margin={frame.margin}
      cells={frame.cells}
      rail={frame.rail}
      insets={insets}
      currentImage={currentImage}
      userIntent={userIntent}
      setUserIntent={setUserIntent}
      shoppingIntent={shoppingIntent}
      setShoppingIntent={setShoppingIntent}
      includeProducts={includeProducts}
      setIncludeProducts={setIncludeProducts}
      stages={stages}
      hasRun={status !== "idle"}
      warnings={warnings}
      error={error}
      elapsed={elapsed}
      override={override}
      onPick={pick}
      onAnalyze={() => currentImage && analyze(currentImage)}
      onReset={() => {
        reset();
        setCurrentImage(null);
      }}
      onWardrobe={() => navigation.navigate("Wardrobe")}
      onPrevious={() => navigation.navigate("PreviousReads")}
      feedbackGiven={feedbackGiven}
      onFeedback={(recId, verdict) => {
        setFeedback(recId, verdict);
        if (shown?.request_id) {
          submitFeedback({
            request_id: shown.request_id,
            recommendation_id: recId,
            feedback: verdict,
            user_id: userId ?? undefined,
          }).catch(() => {});
        }
      }}
    />
  );

  if (!frame.isDesktop) return <View style={{ flex: 1, backgroundColor: m.ground }}>{body}</View>;

  return (
    <View style={{ flex: 1, flexDirection: "row", backgroundColor: m.ground }}>
      {/* The rail reports the *real* read, never the fixture standing in for
          it. Sourced from `shown` it announced `OBJECT T-SHIRT · ID MOCK-123`
          over a photograph the shopper had just chosen and not yet sent — the
          fixture's identity, presented as theirs, in the one plate on screen
          that is not tagged `"SYNTHETIC"`. Caught on the held frame. The
          fallbacks below were already written; they were unreachable. */}
      <Rail
        object={
          result?.detected_attributes?.clothing_type?.toUpperCase() ??
          (currentImage ? "HELD, NOT READ" : "NONE HELD")
        }
        objectId={result?.request_id?.toUpperCase() ?? (shown ? "SYNTHETIC" : "—")}
        activeZone={ZONE.read}
        onRead={() => {}}
        onWardrobe={() => navigation.navigate("Wardrobe")}
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

// ── The plane ────────────────────────────────────────────────────────────

interface PlaneProps {
  phase: ReadPhase;
  synthetic: boolean;
  shown: StreamAnalysisResult | null;
  frameIsDesktop: boolean;
  width: number;
  margin: number;
  cells: number;
  rail: number;
  insets: { top: number; bottom: number };
  currentImage: string | null;
  userIntent: string;
  setUserIntent: (v: string) => void;
  shoppingIntent: ShoppingIntent;
  setShoppingIntent: (v: ShoppingIntent) => void;
  includeProducts: boolean;
  setIncludeProducts: (v: boolean) => void;
  stages: ReturnType<typeof useAnalysisScope>["stages"];
  hasRun: boolean;
  warnings: string[];
  error: string | null;
  elapsed: number;
  override: ReadPhase | null;
  onPick: (from: "library" | "camera") => void;
  onAnalyze: () => void;
  onReset: () => void;
  onWardrobe: () => void;
  onPrevious: () => void;
  feedbackGiven: Record<string, "like" | "dislike">;
  onFeedback: (recId: string, verdict: "like" | "dislike") => void;
}

function Plane(p: PlaneProps) {
  const { material: m } = useTheme();
  const plane = p.width - p.rail;
  /** The window figure is the fallback for the very first frame only; the
   *  split is composed from the measured plane, so the scrollbar cannot push
   *  the outfit pane off the right edge. */
  const [paneW, onPaneLayout] = useMeasuredWidth();
  const content = paneW ?? plane - p.margin * 2;

  /** Desktop splits two parts read to three parts outfit. The read pane at
   *  424 holds the display ramp's d4 step, which is where the five words step
   *  down to once the outfit is up; while the read owns the whole plane they
   *  set at d5. That step is a real event, not a breakpoint hack — the
   *  stencil shrinks as the outfit arrives. */
  const split = p.frameIsDesktop && p.phase !== "reading";
  const readW = split ? Math.round((content - grid.gutter) * 0.4) : content;
  const outfitW = split ? content - grid.gutter - readW : content;
  const stencilRole = p.frameIsDesktop && !split ? type.stencilDesktop : type.stencilPhone;

  const attrs = p.shown?.detected_attributes ?? null;
  /** Phase 10 paces this off the stream. Here it is all-or-nothing, which is
   *  what a finished read and a fast response both look like anyway. */
  const arrived = p.phase === "reading" ? 3 : 5;
  const rows = wordRows(attrs, arrived);

  /** Measured, not derived — see `useMeasuredWidth`. */
  const [gridW, onGridLayout] = useMeasuredWidth();

  const rec = p.shown?.recommendations?.[0] ?? null;
  const flags = p.shown?.errors ?? [];
  const pieces: RecommendationItem[] = rec
    ? [...(attrs ? [readGarment(attrs)] : []), ...rec.items]
    : [];
  const cell = cellSize(gridW ?? outfitW, p.cells);

  const readPane = (
    <View style={{ width: split ? readW : undefined }}>
      <Zone
        name={ZONE.read}
        state={
          p.phase === "empty"
            ? "NOTHING HELD · ONE GARMENT, PHOTOGRAPHED"
            : p.phase === "held"
              ? "HELD, NOT SENT · NOTHING HAS RUN"
              : p.phase === "reading"
                ? "THE STREAM IS OPEN"
                : p.phase === "struck"
                  ? "THE VISION PASS FAILED — THIS IS FATAL, THE REST IS NOT"
                  : `READ IN ${p.elapsed ? `${p.elapsed.toFixed(1)}S` : "ONE PASS"}`
        }
      />

      {/* The primary action sits at the top of the read pane on desktop and is
          foot-pinned on the phone, per the two FIRST VIEWPORT blocks. */}
      {p.frameIsDesktop ? <Actions {...p} style={{ marginBottom: space.s3 }} /> : null}

      {p.userIntent.trim() && p.phase !== "empty" ? (
        <IntentStamp text={p.userIntent} desktop={p.frameIsDesktop} />
      ) : null}

      {p.phase === "empty" || p.phase === "held" ? (
        <View style={{ marginBottom: space.s3 }}>
          <IntentField value={p.userIntent} onChange={p.setUserIntent} />
        </View>
      ) : null}

      <GarmentPort
        uri={p.currentImage}
        height={
          !p.currentImage
            ? p.frameIsDesktop
              ? 220
              : 190
            : /* Once the words exist, the photograph's job changes from
                 subject to reference, so on the split desktop plane it drops
                 to a strip and the five words come up into the first
                 viewport. Measured on screen: at full height the read pane
                 pushed every word below the fold, which put the thesis of
                 the surface out of sight on the frame the client judges it
                 on. The phone keeps it tall — there the words follow it in
                 one scroll. */
              p.frameIsDesktop && (p.phase === "read" || p.phase === "struck")
              ? 260
              : Math.round(Math.min(readW, 520) * 1.15)
        }
        state={
          p.phase === "reading"
            ? '"READING"'
            : p.phase === "read"
              ? '"READ"'
              : p.phase === "struck"
                ? '"STRUCK"'
                : p.currentImage
                  ? '"HELD"'
                  : '"EMPTY"'
        }
        note={p.currentImage ? "YOUR PHOTOGRAPH · SENT ONCE" : undefined}
        style={{ marginBottom: space.s3 }}
      />

      {p.phase === "struck" ? (
        <Struck error={p.error} onReset={p.onReset} />
      ) : null}

      {p.phase === "reading" ? <Stages stages={p.stages} /> : null}

      {/* The five words. In `empty` they belong to the worked read below, so
          they are not printed here — the port has nothing to have read. */}
      {p.phase === "reading" || p.phase === "read" ? (
        <View style={{ marginTop: space.s2 }}>
          <WordStack rows={rows} size={stencilRole} />
          <CodeBlock
            lines={[
              "FIVE SLOTS, FOUR HEADS — SECONDARY COLOUR SHARES THE COLOUR HEAD",
              attrs?.description_relevant && attrs.description
                ? attrs.description.toUpperCase()
                : null,
            ]}
            style={{ marginTop: space.s2 }}
          />
        </View>
      ) : null}

      {p.phase === "held" ? (
        <CodeBlock
          lines={[
            "NOTHING HAS BEEN SENT YET — THE PHOTOGRAPH IS STILL ON YOUR DEVICE",
            "SEND IT AND THE VISION PASS RETURNS FIVE WORDS AND FOUR CONFIDENCES",
          ]}
        />
      ) : null}

      {p.phase === "empty" || p.phase === "held" ? (
        <View style={{ marginTop: space.s3, gap: space.s2 }}>
          <Selector
            label="Shopping intent"
            options={SHOPPING_INTENTS}
            value={p.shoppingIntent}
            onChange={p.setShoppingIntent}
            note="WHICH SIDE OF THE CATALOG THE SHOPPING STAGE SEARCHES"
          />
          <WordSwitch
            name="SHOPPING"
            on={p.includeProducts}
            onChange={p.setIncludeProducts}
            whenOn="SLOTS YOUR CLOSET CANNOT FILL GET PRICED"
            whenOff="WARDROBE ONLY — NOTHING IS PRICED"
          />
        </View>
      ) : null}
    </View>
  );

  const outfitPane =
    p.phase === "reading" ? null : (
      <View style={{ width: split ? outfitW : undefined }}>
        <Zone
          name={p.synthetic ? WORKED : ZONE.outfit}
          state={
            p.synthetic
              ? `NOT YOUR GARMENT · FROM THE PROJECT'S OWN TEST FIXTURE${
                  p.override ? " · CAPTURE HARNESS" : ""
                }`
              : rec
                ? `${rec.items.filter((i) => i.owned).length} OF ${rec.items.length} ALREADY YOURS · CONFIDENCE ${rec.confidence.toFixed(2)}${
                    p.override ? " · CAPTURE HARNESS" : ""
                  }`
                : "NOTHING BUILT YET"
          }
          right={p.synthetic ? <SyntheticTag /> : null}
        />

        {p.synthetic ? (
          <View style={{ marginBottom: space.s3 }}>
            <Text style={[type.stampPhone, { color: m.ink }]}>
              {`"${SYNTHETIC_INTENT.toUpperCase()}"`}
            </Text>
            <Code style={{ marginTop: space.s1 }}>
              THE REQUEST THIS WORKED READ ANSWERS
            </Code>
          </View>
        ) : null}

        {/* In `empty` the five words are the worked read's, so they print
            here, under its own zone head and its own synthetic tag. */}
        {p.synthetic ? (
          <View style={{ marginBottom: space.s4 }}>
            <WordStack rows={rows} size={stencilRole} />
            <Code style={{ marginTop: space.s2 }}>
              FIVE SLOTS, FOUR HEADS — SECONDARY COLOUR SHARES THE COLOUR HEAD
            </Code>
          </View>
        ) : null}

        {pieces.length > 0 ? (
          <View
            onLayout={onGridLayout}
            style={{ flexDirection: "row", flexWrap: "wrap", gap: grid.gutter }}
          >
            {gridW === null ? null : pieces.map((item, i) => (
              <PiecePlate
                key={`${item.item_type}-${i}`}
                item={item}
                size={cell}
                isRead={i === 0 && !!attrs}
                flagged={flags.length > 0 && !item.owned && !!item.products?.length}
              />
            ))}
            {gridW !== null && pieces.length < p.cells
              ? Array.from({ length: p.cells - pieces.length }).map((_, i) => (
                  <OpenSlot key={`open-${i}`} label="OPEN" size={cell} />
                ))
              : null}
          </View>
        ) : (
          <Plate struck>
            <Text style={[type.plateTitle, { color: m.ink }]}>{'"NOT BUILT YET"'}</Text>
            <Code style={{ marginTop: 3 }}>
              THE OUTFIT IS ASSEMBLED AFTER THE GARMENT IS READ
            </Code>
          </Plate>
        )}

        {/* A flagged claim is struck with hazard tape, not quietly dropped. */}
        {flags.length > 0 ? (
          <View style={{ marginTop: space.s4 }}>
            <Hazard />
            <Plate heavy style={{ marginTop: space.s1 }}>
              <Text style={[type.plateTitle, { color: m.ink }]}>{'"FLAGGED"'}</Text>
              {flags.map((f) => (
                <Text
                  key={f}
                  style={[type.bodySmall, { color: m.ink, marginTop: 4, maxWidth: bodyMeasure }]}
                >
                  {f}
                </Text>
              ))}
              <Code style={{ marginTop: space.s1 }}>
                THE VERIFIER CHECKED THE CLAIM AND COULD NOT STAND IT UP · THE PIECE IS STILL SHOWN
              </Code>
            </Plate>
            <Hazard />
          </View>
        ) : null}

        {rec?.overall_explanation ? (
          <View style={{ marginTop: space.s4, maxWidth: bodyMeasure }}>
            <Text style={[type.body, { color: m.ink }]}>{rec.overall_explanation}</Text>
            <CodeBlock
              lines={[
                rec.evidence?.length ? rec.evidence.join(" · ").toUpperCase() : null,
                rec.style_tags?.length
                  ? `TAGS ${rec.style_tags.join(" · ").replace(/_/g, " ").toUpperCase()}`
                  : null,
              ]}
              style={{ marginTop: space.s2 }}
            />
          </View>
        ) : null}

        {p.phase === "read" && rec ? (
          <Feedback
            recId={rec.id}
            given={p.feedbackGiven[rec.id]}
            onFeedback={p.onFeedback}
          />
        ) : null}
      </View>
    );

  const scroll = (
    <ScrollView
      style={{ flex: 1, backgroundColor: m.ground }}
      contentContainerStyle={{
        paddingHorizontal: p.margin,
        paddingTop: p.insets.top + space.s4,
        paddingBottom: (p.frameIsDesktop ? space.s6 : space.s8) + p.insets.bottom,
      }}
    >
      {!p.frameIsDesktop ? (
        <Head onWardrobe={p.onWardrobe} onPrevious={p.onPrevious} />
      ) : null}

      {p.frameIsDesktop ? (
        <View
          onLayout={onPaneLayout}
          style={{ flexDirection: "row", gap: grid.gutter, alignItems: "flex-start" }}
        >
          {readPane}
          {outfitPane}
        </View>
      ) : (
        <>
          {readPane}
          <Rule style={{ marginVertical: space.s5 }} heavy />
          {outfitPane}
          <View style={{ marginTop: space.s5 }}>
            <SystemStatusPlate
              stages={p.stages}
              hasRun={p.hasRun}
              includeProducts={p.includeProducts}
              warnings={p.warnings}
            />
          </View>
        </>
      )}
    </ScrollView>
  );

  if (p.frameIsDesktop) return scroll;

  /** The phone pins the action to the foot, within thumb reach, over the
   *  scroll. It is the only pinned thing on the surface. */
  return (
    <View style={{ flex: 1 }}>
      {scroll}
      <ReadFoot bottom={p.insets.bottom}>
        <Actions {...p} />
      </ReadFoot>
    </View>
  );
}

// ── Parts ────────────────────────────────────────────────────────────────

/** The phone head. The mark, unquoted, and the two layers as words. No badge
 *  pill, no lightning bolt, no claim that the product uses AI. */
function Head({ onWardrobe, onPrevious }: { onWardrobe: () => void; onPrevious: () => void }) {
  const { material: m } = useTheme();
  const history = useAppStore((s) => s.analysisHistory);

  return (
    <View style={{ marginBottom: space.s4 }}>
      {/* The mark and the material switch share the top line. The switch was
          in the zone head's right slot and pushed `"THE READ"` onto two lines
          at 390 — apparatus crowding the zone name, which is the one thing on
          the surface that says where you are. */}
      <View style={{ flexDirection: "row", alignItems: "flex-start", gap: space.s2 }}>
        <Text style={[type.zone, { color: m.ink, flex: 1 }]}>SYNCLOOK</Text>
        <MaterialSwitch />
      </View>
      <View style={{ flexDirection: "row", gap: space.s3, marginTop: space.s2 }}>
        <Pressable onPress={onWardrobe} accessibilityRole="link" style={{ minHeight: 44, justifyContent: "center" }}>
          <Text style={[type.plateTitle, { color: m.ink }]}>{ZONE.wardrobe}</Text>
          <Code>WHAT YOU OWN</Code>
        </Pressable>
        <Pressable onPress={onPrevious} accessibilityRole="link" style={{ minHeight: 44, justifyContent: "center" }}>
          <Text style={[type.plateTitle, { color: m.ink }]}>{ZONE.previousReads}</Text>
          <Code>{`${history.length} ON FILE`}</Code>
        </Pressable>
      </View>
      <View style={{ height: surface.rule, backgroundColor: m.strokeHeavy, marginTop: space.s2 }} />
    </View>
  );
}

function SyntheticTag() {
  const { material: m } = useTheme();
  return (
    <Plate heavy>
      <Text style={[type.plateTitle, { color: m.ink }]}>{SYNTHETIC}</Text>
    </Plate>
  );
}

function Actions(p: PlaneProps & { style?: object }) {
  const held = !!p.currentImage;
  const reading = p.phase === "reading";
  const done = p.phase === "read";
  const struck = p.phase === "struck";

  /** One primary action, whose word says what pressing it does in this phase.
   *  Never a second competing fill — the orange field is the only one on the
   *  surface, which is what makes it mean "this is the act". */
  const label = reading
    ? '"READING…"'
    : done
      ? '"READ ANOTHER"'
      : struck
        ? '"TRY AGAIN"'
        : held
          ? '"READ IT"'
          : '"READ A GARMENT"';

  return (
    <View style={[{ gap: space.s2 }, p.style]}>
      <ActionPlate
        label={label}
        note={
          reading
            ? "THE STREAM IS OPEN"
            : done
              ? "CLEARS THIS READ AND TAKES A NEW PHOTOGRAPH"
              : struck
                ? "SENDS THE SAME PHOTOGRAPH AGAIN"
                : held
                  ? "SENDS THE PHOTOGRAPH AND YOUR REQUEST"
                  : "CHOOSE A PHOTOGRAPH OF ONE GARMENT"
        }
        disabled={reading}
        onPress={() => {
          if (done) return p.onPick("library");
          if (held) return p.onAnalyze();
          return p.onPick("library");
        }}
      />
      <View style={{ flexDirection: "row", gap: space.s2 }}>
        {held && !reading && !done ? (
          <SecondaryPlate
            label='"CHOOSE ANOTHER"'
            onPress={() => p.onPick("library")}
            style={{ flex: 1 }}
          />
        ) : null}
        {Platform.OS !== "web" && !reading ? (
          <SecondaryPlate
            label='"USE THE CAMERA"'
            onPress={() => p.onPick("camera")}
            style={{ flex: 1 }}
          />
        ) : null}
        {held && !reading ? (
          <SecondaryPlate label='"CLEAR"' onPress={p.onReset} style={{ flex: 1 }} />
        ) : null}
      </View>
    </View>
  );
}

/** The stages, while the stream is open. Phase 10 replaces this with the
 *  authored moment; it exists here so `reading` renders and so the phase is
 *  structurally correct — named stages, text equivalents, no spinner and no
 *  determinate bar over an indeterminate process. */
function Stages({ stages }: { stages: PlaneProps["stages"] }) {
  const { material: m } = useTheme();
  return (
    <View style={{ marginBottom: space.s3 }}>
      {stages.map((s) => (
        <View
          key={s.stage}
          style={{ flexDirection: "row", alignItems: "baseline", gap: space.s2, marginTop: 3 }}
        >
          <Text
            style={[
              type.plateValue,
              { color: m.ink, opacity: s.status === "pending" ? dim : 1, flex: 1 },
            ]}
            numberOfLines={1}
          >
            {STAGE_WORD[s.stage] ?? `"${s.stage.toUpperCase()}"`}
          </Text>
          <Code full={s.status !== "pending"}>
            {s.status === "done"
              ? "RAN"
              : s.status === "active"
                ? "RUNNING"
                : s.status === "error"
                  ? "FAILED"
                  : "PENDING"}
          </Code>
        </View>
      ))}
      <Code style={{ marginTop: space.s2 }}>
        PHASE 10 AUTHORS THIS WAIT · THE STAGES ABOVE ARE THE STREAM&apos;S OWN NAMES
      </Code>
    </View>
  );
}

/** Vision failure is fatal — every other stage returns partial results. So the
 *  struck state is a plate the reader must act on, not v1's 11pt grey
 *  footnote under the primary button. */
function Struck({ error, onReset }: { error: string | null; onReset: () => void }) {
  const { material: m } = useTheme();
  return (
    <View style={{ marginBottom: space.s3 }}>
      <Plate heavy>
        <Text style={[type.zoneSmall, { color: m.ink }]}>{'"COULD NOT READ IT"'}</Text>
        <Text style={[type.bodySmall, { color: m.ink, marginTop: 4, maxWidth: bodyMeasure }]}>
          {error ?? "The vision pass did not return."}
        </Text>
        <CodeBlock
          lines={[
            "THE VISION PASS IS THE ONE STAGE THAT CANNOT DEGRADE — WITHOUT IT THERE IS NO GARMENT",
            "ONE GARMENT, FILLING THE FRAME, IN THE BEST LIGHT YOU HAVE",
          ]}
          style={{ marginTop: space.s2 }}
        />
      </Plate>
      <SecondaryPlate
        label='"TRY ANOTHER PHOTOGRAPH"'
        heavy
        onPress={onReset}
        style={{ marginTop: space.s2 }}
      />
    </View>
  );
}

function Feedback({
  recId,
  given,
  onFeedback,
}: {
  recId: string;
  given?: "like" | "dislike";
  onFeedback: (recId: string, verdict: "like" | "dislike") => void;
}) {
  return (
    <View style={{ marginTop: space.s4, flexDirection: "row", gap: space.s2 }}>
      <SecondaryPlate
        label={given === "like" ? '"GOOD READ" · SENT' : '"GOOD READ"'}
        heavy={given === "like"}
        onPress={() => onFeedback(recId, "like")}
        style={{ flex: 1 }}
      />
      <SecondaryPlate
        label={given === "dislike" ? '"WRONG" · SENT' : '"WRONG"'}
        heavy={given === "dislike"}
        onPress={() => onFeedback(recId, "dislike")}
        style={{ flex: 1 }}
      />
    </View>
  );
}

/** The foot-pinned action. Phone only — the contract pins it within thumb
 *  reach and the desktop composition puts it at the top of the read pane
 *  instead. */
function ReadFoot(props: { children: React.ReactNode; bottom: number }) {
  const { material: m } = useTheme();
  return (
    <View
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: m.ground,
        borderTopWidth: surface.rule,
        borderTopColor: m.strokeHeavy,
        paddingHorizontal: grid.marginPhone,
        paddingTop: space.s2,
        paddingBottom: props.bottom + space.s2,
      }}
    >
      {props.children}
    </View>
  );
}
