import { BASE_URL } from "./client";
import type { ShoppingIntent, StreamAnalysisResult } from "../types/api";

export type AnalysisStage =
  | "start"
  | "vision"
  | "styling"
  | "recommendation"
  | "shopping";

export interface StreamCallbacks {
  onStageStart: (stage: AnalysisStage, message: string) => void;
  onStageDone: (stage: AnalysisStage) => void;
  onResult: (data: StreamAnalysisResult) => void;
  onDone: (elapsedSeconds: number) => void;
  onError: (stage: string, error: string) => void;
  onWarning: (stage: string, error: string) => void;
}

/**
 * Stream an image analysis with real-time SSE progress events.
 * Returns a cleanup function to abort the stream.
 */
export function streamAnalysis(
  imageUri: string,
  userId: string | undefined,
  callbacks: StreamCallbacks,
  shoppingIntent: ShoppingIntent = "unisex",
  includeProducts: boolean = true
): () => void {
  const abortController = new AbortController();

  (async () => {
    try {
      const { buildImageFormData } = await import("./endpoints");
      const formData = await buildImageFormData(imageUri);

      const params = new URLSearchParams();
      if (userId) params.set("user_id", userId);
      params.set("shopping_intent", shoppingIntent);
      params.set("include_products", String(includeProducts));
      const url = `${BASE_URL}/api/v1/analyze/stream?${params.toString()}`;

      const response = await fetch(url, {
        method: "POST",
        body: formData,
        signal: abortController.signal,
        headers: {
          Accept: "text/event-stream",
        },
      });

      if (!response.ok || !response.body) {
        callbacks.onError("stream", `HTTP ${response.status}`);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let currentEvent = "";
      let currentData = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Normalise \r\n and \r to \n so the parser works regardless of
        // what line endings sse-starlette uses.
        const normalised = buffer.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
        const lines = normalised.split("\n");

        // Keep the last (possibly incomplete) line in the buffer.
        buffer = lines.pop() ?? "";

        for (const raw of lines) {
          const line = raw;
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            const payload = line.slice(5);
            const normalizedPayload = payload.startsWith(" ")
              ? payload.slice(1)
              : payload;
            currentData = currentData
              ? `${currentData}\n${normalizedPayload}`
              : normalizedPayload;
          } else if (line === "") {
            // Blank line = end of one SSE message
            if (currentEvent && currentData) {
              try {
                const parsed = JSON.parse(currentData);
                handleSSEEvent(currentEvent, parsed, callbacks);
              } catch {
                // malformed JSON — skip
              }
            }
            currentEvent = "";
            currentData = "";
          }
        }
      }

      // Flush anything left in the buffer after stream closes
      if (currentEvent && currentData) {
        try {
          const parsed = JSON.parse(currentData);
          handleSSEEvent(currentEvent, parsed, callbacks);
        } catch {
          // ignore
        }
      }
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        callbacks.onError("stream", err?.message ?? "Stream failed");
      }
    }
  })();

  return () => abortController.abort();
}

function handleSSEEvent(
  event: string,
  data: Record<string, any>,
  callbacks: StreamCallbacks
): void {
  switch (event) {
    case "status":
      callbacks.onStageStart(data.stage as AnalysisStage, data.message);
      break;
    case "agent_done":
      callbacks.onStageDone(data.stage as AnalysisStage);
      break;
    case "warning":
      callbacks.onWarning(data.stage ?? "unknown", data.error ?? data.message ?? "");
      break;
    case "error":
      callbacks.onError(data.stage ?? "unknown", data.error ?? data.message ?? "");
      break;
    case "result":
      callbacks.onResult(data as StreamAnalysisResult);
      break;
    case "done":
      callbacks.onDone(data.elapsed_s ?? 0);
      break;
    default:
      break;
  }
}
