/** `"SYSTEM STATUS"` — Plan v2 Phase 9.
 *
 *  This plate is what replaced v1's Landing screen. Landing's nominal job was
 *  proving the system is real, and it did it with three numbered circles under
 *  "How it works" — a *claim* about the machine. This is the same job
 *  discharged as *evidence*: which stages ran on the last real request, which
 *  the planner skipped, which the verifier flagged, and whether the API
 *  answered at all. Permanent in the desktop rail, foot plate on the phone.
 *
 *  Every line reads a value the frontend genuinely has: `useAnalysis`'s stage
 *  machine, the store's `includeProducts`, and one `GET /health`. Nothing here
 *  infers a key, a catalog size, an uptime or a user count — PRODUCT.md marks
 *  all of those unfabricable, and a status plate that guesses is worse than no
 *  plate.
 *
 *  Graceful degradation is a designed property of the backend, so the reduced
 *  states are the normal reading of this plate rather than its error case:
 *  `"SKIPPED"` against `wardrobe` is what no-match looks like, `"OFF"` against
 *  `shopping` is what the shopper's own switch or a missing SerpAPI key looks
 *  like, and `"NO ANSWER"` against the API is what a dead backend looks like.
 */

import React from "react";
import { View } from "react-native";

import { checkHealth } from "../api/endpoints";
import type { StageState } from "../hooks/useAnalysis";
import { space } from "../theme/material";
import { Code, CodeRow } from "./Margin";
import { Plate } from "./Plate";

type Api = { state: "CHECKING" | "ON" | "NO ANSWER"; version?: string };

/** One ping on mount. Not a poll: a status plate that re-requests every few
 *  seconds is a load generator, and the honest window is "when you opened the
 *  app". */
export function useApiStatus(): Api {
  const [api, setApi] = React.useState<Api>({ state: "CHECKING" });

  React.useEffect(() => {
    let live = true;
    checkHealth()
      .then((h) => live && setApi({ state: "ON", version: h.version }))
      .catch(() => live && setApi({ state: "NO ANSWER" }));
    return () => {
      live = false;
    };
  }, []);

  return api;
}

const WORD: Record<StageState["status"], string> = {
  pending: '"PENDING"',
  active: '"RUNNING"',
  done: '"RAN"',
  error: '"FAILED"',
};

export function SystemStatusPlate({
  stages,
  hasRun,
  includeProducts,
  warnings,
  nameWidth = 115,
  stacked = false,
}: {
  stages: StageState[];
  hasRun: boolean;
  includeProducts: boolean;
  warnings: string[];
  /** Two-column mode's name column. 115 because the longest stage name,
   *  `RECOMMENDATION`, measures 112pt in Martian Mono 10/12 at 1pt tracking —
   *  measured in the browser, not estimated. At the previous 104 it broke
   *  mid-word on the phone foot plate: `RECOMMENDATIO` / `N`. */
  nameWidth?: number;
  /** Rail mode: the stage name on its own line with its state word under it.
   *  Two columns need ~165pt to hold `RECOMMENDATION` against `"RUNNING"`,
   *  and the rail has 159 — measured on screen, where the name broke
   *  mid-word and every value wrapped. The rail has vertical room and no
   *  horizontal room, so the rail stacks. */
  stacked?: boolean;
}) {
  const api = useApiStatus();

  return (
    <Plate>
      <Code full>{'"SYSTEM STATUS"'}</Code>
      <View style={{ marginTop: space.s1 }}>
        <Line
          stacked={stacked}
          name="API"
          value={api.state === "ON" ? `"ON" · V${api.version ?? "?"}` : `"${api.state}"`}
          nameWidth={nameWidth}
        />
        {stages.map((s) => {
          const off = s.stage === "shopping" && !includeProducts;
          const value = off
            ? '"OFF" · YOUR SWITCH'
            : hasRun
              ? WORD[s.status]
              : '"NO RUN"';
          return (
            <Line
              key={s.stage}
              stacked={stacked}
              name={s.stage.toUpperCase()}
              value={value}
              nameWidth={nameWidth}
            />
          );
        })}
        {warnings.length > 0 ? (
          <Line
            stacked={stacked}
            name="FLAGGED"
            value={`${warnings.length}`}
            nameWidth={nameWidth}
          />
        ) : null}
      </View>
      <Code style={{ marginTop: space.s2 }}>
        A SKIPPED STAGE READS &quot;PENDING&quot; · NOT AN ERROR
      </Code>
    </Plate>
  );
}

function Line({
  stacked,
  name,
  value,
  nameWidth,
}: {
  stacked: boolean;
  name: string;
  value: string;
  nameWidth: number;
}) {
  if (!stacked) return <CodeRow name={name} value={value} nameWidth={nameWidth} />;
  return (
    <View style={{ marginBottom: 4 }}>
      <Code>{name}</Code>
      <Code full>{value}</Code>
    </View>
  );
}
