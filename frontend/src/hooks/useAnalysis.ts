import { useCallback, useRef, useState } from "react";
import { streamAnalysis, type AnalysisStage } from "../api/sse";
import { useAppStore } from "../store/useAppStore";
import * as Haptics from "expo-haptics";
import type { StreamAnalysisResult } from "../types/api";

export type AnalysisStatus = "idle" | "analyzing" | "done" | "error";

export interface StageState {
  stage: AnalysisStage;
  status: "pending" | "active" | "done" | "error";
  message: string;
}

// The graph decides at runtime whether wardrobe/shopping run, so stages the
// stream never mentions are dropped from the display when the run completes.
const INITIAL_STAGES: StageState[] = [
  { stage: "intent", status: "pending", message: "Understanding your request..." },
  { stage: "vision", status: "pending", message: "Analyzing image..." },
  { stage: "styling", status: "pending", message: "Generating style matches..." },
  { stage: "recommendation", status: "pending", message: "Building recommendations..." },
  { stage: "wardrobe", status: "pending", message: "Checking your wardrobe..." },
  { stage: "shopping", status: "pending", message: "Finding products online..." },
  { stage: "verifier", status: "pending", message: "Quality-checking recommendations..." },
];

function mergeUniqueMessages(existing: string[], incoming: string[]): string[] {
  const merged = [...existing];
  for (const message of incoming) {
    if (!message) continue;
    if (!merged.includes(message)) {
      merged.push(message);
    }
  }
  return merged;
}

export function useAnalysis() {
  const [status, setStatus] = useState<AnalysisStatus>("idle");
  const [stages, setStages] = useState<StageState[]>(INITIAL_STAGES);
  const [result, setResult] = useState<StreamAnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [elapsed, setElapsed] = useState<number>(0);
  const cancelRef = useRef<(() => void) | null>(null);
  const userId = useAppStore((s) => s.userId);
  const shoppingIntent = useAppStore((s) => s.shoppingIntent);
  const includeProducts = useAppStore((s) => s.includeProducts);
  const userIntent = useAppStore((s) => s.userIntent);
  const setLastAnalysis = useAppStore((s) => s.setLastAnalysis);
  const setLastWarnings = useAppStore((s) => s.setLastWarnings);
  const addToHistory = useAppStore((s) => s.addToHistory);

  const updateStage = useCallback(
    (stage: AnalysisStage, patch: Partial<StageState>) => {
      setStages((prev) =>
        prev.map((s) => (s.stage === stage ? { ...s, ...patch } : s))
      );
    },
    []
  );

  const analyze = useCallback(
    (imageUri: string) => {
      setStatus("analyzing");
      setError(null);
      setResult(null);
      setWarnings([]);
      setLastWarnings([]);
      setStages(INITIAL_STAGES);

      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

      const cancel = streamAnalysis(imageUri, userId ?? undefined, {
        onStageStart: (stage, message) => {
          updateStage(stage, { status: "active", message });
        },
        onStageDone: (stage) => {
          updateStage(stage, { status: "done" });
        },
        onResult: (data) => {
          setResult(data);
          setLastAnalysis(data);
          addToHistory(data);

          const streamErrors = data.errors ?? [];
          if (streamErrors.length > 0) {
            setWarnings((prev) => {
              const merged = mergeUniqueMessages(prev, streamErrors);
              setLastWarnings(merged);
              return merged;
            });
          }
        },
        onDone: (elapsedSeconds) => {
          setElapsed(elapsedSeconds);
          setStatus("done");
          // Drop stages the planner never routed through (e.g. wardrobe
          // without a user, shopping when the intent declined it).
          setStages((prev) => prev.filter((s) => s.status !== "pending"));
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        },
        onError: (stage, errMsg) => {
          updateStage(stage as AnalysisStage, { status: "error", message: errMsg });
          setError(errMsg);
          setStatus("error");
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
        },
        onWarning: (stage, warnMsg) => {
          updateStage(stage as AnalysisStage, {
            status: "done",
            message: warnMsg,
          });
          const warning = `${stage}: ${warnMsg}`;
          setWarnings((prev) => {
            const merged = mergeUniqueMessages(prev, [warning]);
            setLastWarnings(merged);
            return merged;
          });
        },
      }, shoppingIntent, includeProducts, userIntent);

      cancelRef.current = cancel;
    },
    [
      userId,
      shoppingIntent,
      includeProducts,
      userIntent,
      updateStage,
      setLastAnalysis,
      setLastWarnings,
      addToHistory,
    ]
  );

  const cancel = useCallback(() => {
    cancelRef.current?.();
    setStatus("idle");
  }, []);

  const reset = useCallback(() => {
    cancelRef.current?.();
    setStatus("idle");
    setError(null);
    setResult(null);
    setWarnings([]);
    setLastWarnings([]);
    setStages(INITIAL_STAGES);
    setElapsed(0);
  }, [setLastWarnings]);

  return { status, stages, result, error, warnings, elapsed, analyze, cancel, reset };
}
