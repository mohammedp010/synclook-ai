import { create } from "zustand";
import type { ShoppingIntent, StreamAnalysisResult } from "../types/api";

interface AppState {
  // User
  userId: string | null;
  setUserId: (id: string) => void;

  // Shopping intent for product search/filtering
  shoppingIntent: ShoppingIntent;
  setShoppingIntent: (shoppingIntent: ShoppingIntent) => void;

  // Include shopping links in recommendations
  includeProducts: boolean;
  setIncludeProducts: (includeProducts: boolean) => void;

  // Free-text styling request, e.g. "office party under 5000"
  userIntent: string;
  setUserIntent: (userIntent: string) => void;

  // Current image
  currentImage: string | null;
  setCurrentImage: (uri: string | null) => void;

  // Last analysis result
  lastAnalysis: StreamAnalysisResult | null;
  setLastAnalysis: (result: StreamAnalysisResult | null) => void;

  // Last non-fatal warnings from streaming
  lastWarnings: string[];
  setLastWarnings: (warnings: string[]) => void;

  // History
  analysisHistory: StreamAnalysisResult[];
  addToHistory: (result: StreamAnalysisResult) => void;

  // Feedback tracking (recommendation_id → "like" | "dislike")
  feedbackGiven: Record<string, "like" | "dislike">;
  setFeedback: (recommendationId: string, feedback: "like" | "dislike") => void;

  // Theme
  isDark: boolean;
  toggleTheme: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Default identity so wardrobe matching and preference memory work in the
  // demo without a login flow; replaced when real auth lands.
  userId: "demo-user",
  setUserId: (id) => set({ userId: id }),

  shoppingIntent: "unisex",
  setShoppingIntent: (shoppingIntent) => set({ shoppingIntent }),

  includeProducts: true,
  setIncludeProducts: (includeProducts) => set({ includeProducts }),

  userIntent: "",
  setUserIntent: (userIntent) => set({ userIntent }),

  currentImage: null,
  setCurrentImage: (uri) => set({ currentImage: uri }),

  lastAnalysis: null,
  setLastAnalysis: (result) => set({ lastAnalysis: result }),

  lastWarnings: [],
  setLastWarnings: (warnings) => set({ lastWarnings: warnings }),

  analysisHistory: [],
  addToHistory: (result) =>
    set((state) => ({
      analysisHistory: [result, ...state.analysisHistory].slice(0, 20),
    })),

  feedbackGiven: {},
  setFeedback: (recommendationId, feedback) =>
    set((state) => ({
      feedbackGiven: { ...state.feedbackGiven, [recommendationId]: feedback },
    })),

  isDark: true,
  toggleTheme: () => set((state) => ({ isDark: !state.isDark })),
}));
