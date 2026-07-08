# 📱 Synclook — React Native Frontend Integration Guide

> **A complete, production-grade guide for building a stunning mobile frontend** that connects to the Synclook backend. Modern design patterns, smooth animations, responsive layouts, and beautiful SVG illustrations.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Tech Stack](#2-tech-stack)
3. [Project Setup](#3-project-setup)
4. [API Client Layer](#4-api-client-layer)
5. [SSE Streaming Integration](#5-sse-streaming-integration)
6. [Screen-by-Screen Implementation](#6-screen-by-screen-implementation)
7. [SVG Illustrations & Icons](#7-svg-illustrations--icons)
8. [Animation System](#8-animation-system)
9. [Typography & Design Tokens](#9-typography--design-tokens)
10. [Responsive Layout System](#10-responsive-layout-system)
11. [State Management](#11-state-management)
12. [Complete Component Code](#12-complete-component-code)
13. [Testing & Debugging](#13-testing--debugging)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   React Native App                      │
│                                                         │
│  ┌─────────┐   ┌──────────┐   ┌─────────────────────┐  │
│  │  Camera  │   │  Gallery │   │   Analysis Screen   │  │
│  │  Screen  │──▶│  Picker  │──▶│  (SSE Streaming)    │  │
│  └─────────┘   └──────────┘   └─────────────────────┘  │
│                                        │                │
│                                        ▼                │
│                              ┌─────────────────┐       │
│                              │  Results Screen  │       │
│                              │  (Outfit Cards)  │       │
│                              └────────┬────────┘       │
│                                       │                 │
│                              ┌────────▼────────┐       │
│                              │ Feedback System  │       │
│                              │ (Like / Dislike) │       │
│                              └─────────────────┘       │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │        API Client (Axios + EventSource)          │   │
│  └──────────────────────┬──────────────────────────┘   │
└─────────────────────────┼───────────────────────────────┘
                          │ HTTPS
                          ▼
              ┌───────────────────────┐
              │   Synclook API   │
              │   FastAPI Backend     │
              │   POST /analyze       │
              │   POST /analyze/stream│
              │   POST /feedback      │
              │   GET  /health        │
              └───────────────────────┘
```

---

## 2. Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Framework | React Native 0.76+ / Expo SDK 52+ | Cross-platform mobile |
| Navigation | React Navigation 7 | Screen routing with shared element transitions |
| Styling | Nativewind (Tailwind for RN) | Utility-first responsive styling |
| Animations | React Native Reanimated 3 | 60fps gesture-driven animations |
| SVGs | react-native-svg | Custom illustrations & icons |
| HTTP | Axios | REST API calls |
| Streaming | react-native-sse | Server-Sent Events for real-time progress |
| State | Zustand | Lightweight global state |
| Images | expo-image-picker + expo-camera | Image capture & selection |
| Fonts | expo-font + Google Fonts | Inter, Space Grotesk, Outfit |
| Haptics | expo-haptics | Tactile feedback on interactions |

---

## 3. Project Setup

```bash
# Create a new Expo project
npx create-expo-app@latest Synclook --template blank-typescript
cd Synclook

# Install core dependencies
npx expo install react-native-reanimated react-native-gesture-handler \
  react-native-svg react-native-safe-area-context react-native-screens

# Navigation
npm install @react-navigation/native @react-navigation/native-stack \
  @react-navigation/bottom-tabs

# Styling
npm install nativewind tailwindcss

# API & SSE
npm install axios react-native-sse

# State management
npm install zustand

# Image handling
npx expo install expo-image-picker expo-camera expo-file-system

# Fonts & Haptics
npx expo install expo-font @expo-google-fonts/inter \
  @expo-google-fonts/space-grotesk expo-haptics expo-linear-gradient
```

### `tailwind.config.js`

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./App.{js,jsx,ts,tsx}", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#f5f3ff",
          100: "#ede9fe",
          200: "#ddd6fe",
          300: "#c4b5fd",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed",
          700: "#6d28d9",
          800: "#5b21b6",
          900: "#4c1d95",
        },
        surface: {
          primary:   "#0f0f14",
          secondary: "#1a1a24",
          tertiary:  "#24243a",
          elevated:  "#2a2a40",
        },
        accent: {
          coral:  "#ff6b6b",
          mint:   "#51cf66",
          sky:    "#4dabf7",
          gold:   "#ffd43b",
          violet: "#9775fa",
        },
      },
      fontFamily: {
        sans:    ["Inter_400Regular"],
        medium:  ["Inter_500Medium"],
        semi:    ["Inter_600SemiBold"],
        bold:    ["Inter_700Bold"],
        display: ["SpaceGrotesk_700Bold"],
      },
    },
  },
  plugins: [],
};
```

### Recommended `src/` Folder Structure

```
src/
├── api/
│   ├── client.ts              # Axios instance
│   ├── endpoints.ts           # API endpoint functions
│   └── sse.ts                 # SSE streaming helpers
├── components/
│   ├── ui/                    # Reusable atoms
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   ├── ProgressRing.tsx
│   │   └── AnimatedGradient.tsx
│   ├── analysis/
│   │   ├── UploadArea.tsx
│   │   ├── AnalysisProgress.tsx
│   │   └── StageIndicator.tsx
│   ├── results/
│   │   ├── OutfitCard.tsx
│   │   ├── ClothingChip.tsx
│   │   └── FeedbackButtons.tsx
│   └── svg/
│       ├── LogoSvg.tsx
│       ├── HangerIcon.tsx
│       ├── SparkleIcon.tsx
│       └── WardrobeIllustration.tsx
├── screens/
│   ├── HomeScreen.tsx
│   ├── CameraScreen.tsx
│   ├── AnalysisScreen.tsx
│   └── ResultsScreen.tsx
├── store/
│   └── useAppStore.ts
├── theme/
│   ├── colors.ts
│   ├── typography.ts
│   └── spacing.ts
├── hooks/
│   ├── useAnalysis.ts
│   └── useSSE.ts
└── utils/
    └── responsive.ts
```

---

## 4. API Client Layer

### `src/api/client.ts`

```typescript
import axios from "axios";

// Point to your backend — adjust for dev/prod
const BASE_URL = __DEV__
  ? "http://192.168.1.100:8000"  // Your local IP (not localhost for device)
  : "https://api.synclook.ai";

export const api = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  timeout: 120_000, // Vision models can take up to 30s on first load
  headers: {
    Accept: "application/json",
  },
});

// Request interceptor — attach user ID
api.interceptors.request.use((config) => {
  // You can pull userId from Zustand store or AsyncStorage
  return config;
});

// Response interceptor — standardized error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.message ||
      "Something went wrong";
    return Promise.reject(new Error(message));
  }
);
```

### `src/api/endpoints.ts`

```typescript
import { api } from "./client";
import type {
  AnalysisResponse,
  FeedbackRequest,
  HealthResponse,
} from "../types/api";

/**
 * Health check — verify backend is reachable.
 */
export async function checkHealth(): Promise<HealthResponse> {
  const { data } = await api.get("/health");
  return data;
}

/**
 * Upload an image for analysis (non-streaming).
 * Returns the full analysis response when complete.
 */
export async function analyzeImage(
  imageUri: string,
  userId?: string
): Promise<AnalysisResponse> {
  const formData = new FormData();

  // React Native's FormData accepts { uri, type, name }
  formData.append("image", {
    uri: imageUri,
    type: "image/jpeg",
    name: "clothing.jpg",
  } as any);

  const { data } = await api.post("/analyze", formData, {
    params: userId ? { user_id: userId } : undefined,
    headers: { "Content-Type": "multipart/form-data" },
  });

  return data;
}

/**
 * Submit feedback (like/dislike) on a recommendation.
 */
export async function submitFeedback(
  feedback: FeedbackRequest
): Promise<void> {
  await api.post("/feedback", feedback);
}
```

### `src/types/api.ts`

```typescript
export interface ClothingAttributes {
  clothing_type: string;
  primary_color: string;
  secondary_color: string | null;
  pattern: string;
  style: string;
  confidence: number;
  description: string;
}

export interface RecommendationItem {
  item_type: string;
  color: string;
  style: string;
  reason: string;
}

export interface Recommendation {
  id: string;
  items: RecommendationItem[];
  overall_explanation: string;
  style_tags: string[];
  confidence: number;
}

export interface AnalysisResponse {
  request_id: string;
  detected_attributes: ClothingAttributes;
  recommendations: Recommendation[];
  created_at: string;
}

export interface HealthResponse {
  status: string;
  version: string;
}

export interface FeedbackRequest {
  request_id: string;
  recommendation_id: string;
  feedback: "like" | "dislike";
  user_id?: string;
  comment?: string;
}

// SSE Event types
export type SSEEventType =
  | "status"
  | "agent_done"
  | "warning"
  | "error"
  | "result"
  | "done";

export interface SSEEvent {
  event: SSEEventType;
  data: string; // JSON-encoded payload
}

export interface SSEStatusData {
  stage: string;
  message: string;
  request_id?: string;
}

export interface SSEResultData {
  request_id: string;
  detected_attributes: ClothingAttributes | null;
  recommendations: Recommendation[];
  errors: string[] | null;
}

export interface SSEDoneData {
  elapsed_s: number;
}
```

---

## 5. SSE Streaming Integration

This is the most important integration — it enables real-time progress feedback as the AI pipeline runs.

### `src/api/sse.ts`

```typescript
import EventSource from "react-native-sse";

const BASE_URL = __DEV__
  ? "http://192.168.1.100:8000"
  : "https://api.synclook.ai";

export type AnalysisStage =
  | "start"
  | "vision"
  | "styling"
  | "recommendation";

export interface StreamCallbacks {
  onStageStart: (stage: AnalysisStage, message: string) => void;
  onStageDone: (stage: AnalysisStage) => void;
  onResult: (data: any) => void;
  onDone: (elapsedSeconds: number) => void;
  onError: (stage: string, error: string) => void;
  onWarning: (stage: string, error: string) => void;
}

/**
 * Stream an image analysis with real-time progress events.
 *
 * Uses POST with multipart/form-data via fetch + EventSource.
 * Returns a cleanup function to abort the stream.
 */
export function streamAnalysis(
  imageUri: string,
  userId: string | undefined,
  callbacks: StreamCallbacks
): () => void {
  const abortController = new AbortController();

  (async () => {
    try {
      // Build multipart form body
      const formData = new FormData();
      formData.append("image", {
        uri: imageUri,
        type: "image/jpeg",
        name: "clothing.jpg",
      } as any);

      const params = userId ? `?user_id=${encodeURIComponent(userId)}` : "";

      // Use fetch for POST SSE (EventSource only supports GET)
      const response = await fetch(
        `${BASE_URL}/api/v1/analyze/stream${params}`,
        {
          method: "POST",
          body: formData,
          headers: {
            Accept: "text/event-stream",
          },
          signal: abortController.signal,
        }
      );

      if (!response.ok) {
        const text = await response.text();
        callbacks.onError("network", text);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) return;

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep incomplete line

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith("data:") && currentEvent) {
            const data = line.slice(5).trim();
            try {
              const parsed = JSON.parse(data);
              handleSSEEvent(currentEvent, parsed, callbacks);
            } catch {
              // Non-JSON data line, skip
            }
            currentEvent = "";
          }
        }
      }
    } catch (err: any) {
      if (err.name !== "AbortError") {
        callbacks.onError("stream", err.message);
      }
    }
  })();

  return () => abortController.abort();
}

function handleSSEEvent(
  event: string,
  data: any,
  callbacks: StreamCallbacks
) {
  switch (event) {
    case "status":
      callbacks.onStageStart(data.stage, data.message);
      break;
    case "agent_done":
      callbacks.onStageDone(data.stage);
      break;
    case "result":
      callbacks.onResult(data);
      break;
    case "done":
      callbacks.onDone(data.elapsed_s);
      break;
    case "error":
      callbacks.onError(data.stage, data.error);
      break;
    case "warning":
      callbacks.onWarning(data.stage, data.error);
      break;
  }
}
```

### `src/hooks/useAnalysis.ts` — Custom Hook

```typescript
import { useCallback, useRef, useState } from "react";
import { streamAnalysis, AnalysisStage } from "../api/sse";
import { useAppStore } from "../store/useAppStore";
import * as Haptics from "expo-haptics";

export type AnalysisStatus = "idle" | "analyzing" | "done" | "error";

interface StageState {
  stage: AnalysisStage;
  status: "pending" | "active" | "done" | "error";
  message: string;
}

export function useAnalysis() {
  const [status, setStatus] = useState<AnalysisStatus>("idle");
  const [stages, setStages] = useState<StageState[]>([]);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState<number>(0);
  const cancelRef = useRef<(() => void) | null>(null);
  const userId = useAppStore((s) => s.userId);

  const analyze = useCallback(
    (imageUri: string) => {
      setStatus("analyzing");
      setError(null);
      setResult(null);
      setStages([
        { stage: "vision", status: "pending", message: "Analyzing image..." },
        { stage: "styling", status: "pending", message: "Matching styles..." },
        { stage: "recommendation", status: "pending", message: "Building outfits..." },
      ]);

      const cancel = streamAnalysis(imageUri, userId, {
        onStageStart: (stage, message) => {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
          setStages((prev) =>
            prev.map((s) =>
              s.stage === stage ? { ...s, status: "active", message } : s
            )
          );
        },
        onStageDone: (stage) => {
          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
          setStages((prev) =>
            prev.map((s) =>
              s.stage === stage ? { ...s, status: "done" } : s
            )
          );
        },
        onResult: (data) => {
          setResult(data);
        },
        onDone: (elapsedS) => {
          Haptics.notificationAsync(
            Haptics.NotificationFeedbackType.Success
          );
          setElapsed(elapsedS);
          setStatus("done");
        },
        onError: (stage, errorMsg) => {
          Haptics.notificationAsync(
            Haptics.NotificationFeedbackType.Error
          );
          setError(`${stage}: ${errorMsg}`);
          setStatus("error");
        },
        onWarning: (stage, errorMsg) => {
          setStages((prev) =>
            prev.map((s) =>
              s.stage === stage
                ? { ...s, status: "error", message: errorMsg }
                : s
            )
          );
        },
      });

      cancelRef.current = cancel;
    },
    [userId]
  );

  const cancel = useCallback(() => {
    cancelRef.current?.();
    setStatus("idle");
  }, []);

  const reset = useCallback(() => {
    cancelRef.current?.();
    setStatus("idle");
    setStages([]);
    setResult(null);
    setError(null);
    setElapsed(0);
  }, []);

  return { status, stages, result, error, elapsed, analyze, cancel, reset };
}
```

---

## 6. Screen-by-Screen Implementation

### Screen Flow

```
 ╔═══════════════╗     ╔═══════════════╗     ╔═══════════════╗
 ║   Home Screen ║────▶║   Analysis    ║────▶║   Results     ║
 ║               ║     ║   Screen      ║     ║   Screen      ║
 ║  • Upload     ║     ║  • SSE stages ║     ║  • Outfit     ║
 ║  • Camera     ║     ║  • Progress   ║     ║    cards      ║
 ║  • History    ║     ║    animation  ║     ║  • Feedback   ║
 ╚═══════════════╝     ╚═══════════════╝     ╚═══════════════╝
```

### Navigation Setup — `App.tsx`

```tsx
import React from "react";
import { NavigationContainer, DefaultTheme } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import {
  useFonts,
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
} from "@expo-google-fonts/inter";
import {
  SpaceGrotesk_700Bold,
} from "@expo-google-fonts/space-grotesk";

import HomeScreen from "./src/screens/HomeScreen";
import AnalysisScreen from "./src/screens/AnalysisScreen";
import ResultsScreen from "./src/screens/ResultsScreen";

const Stack = createNativeStackNavigator();

const DarkTheme = {
  ...DefaultTheme,
  dark: true,
  colors: {
    ...DefaultTheme.colors,
    primary: "#8b5cf6",
    background: "#0f0f14",
    card: "#1a1a24",
    text: "#f8fafc",
    border: "#24243a",
    notification: "#ff6b6b",
  },
};

export default function App() {
  const [fontsLoaded] = useFonts({
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
    SpaceGrotesk_700Bold,
  });

  if (!fontsLoaded) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <NavigationContainer theme={DarkTheme}>
        <StatusBar style="light" />
        <Stack.Navigator
          screenOptions={{
            headerShown: false,
            animation: "slide_from_right",
            contentStyle: { backgroundColor: "#0f0f14" },
          }}
        >
          <Stack.Screen name="Home" component={HomeScreen} />
          <Stack.Screen
            name="Analysis"
            component={AnalysisScreen}
            options={{ animation: "fade_from_bottom" }}
          />
          <Stack.Screen
            name="Results"
            component={ResultsScreen}
            options={{ animation: "slide_from_right" }}
          />
        </Stack.Navigator>
      </NavigationContainer>
    </GestureHandlerRootView>
  );
}
```

---

## 7. SVG Illustrations & Icons

### `src/components/svg/LogoSvg.tsx`

```tsx
import React from "react";
import Svg, { Path, Circle, Defs, LinearGradient, Stop, G } from "react-native-svg";
import Animated, {
  useAnimatedProps,
  useSharedValue,
  withRepeat,
  withTiming,
  Easing,
} from "react-native-reanimated";
import { useEffect } from "react";

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

interface LogoSvgProps {
  size?: number;
  animated?: boolean;
}

export function LogoSvg({ size = 48, animated = true }: LogoSvgProps) {
  const pulse = useSharedValue(1);

  useEffect(() => {
    if (animated) {
      pulse.value = withRepeat(
        withTiming(1.15, { duration: 2000, easing: Easing.inOut(Easing.ease) }),
        -1,
        true
      );
    }
  }, [animated]);

  const animatedProps = useAnimatedProps(() => ({
    opacity: 0.3 + 0.2 * (pulse.value - 1),
    r: 18 * pulse.value,
  }));

  return (
    <Svg width={size} height={size} viewBox="0 0 64 64" fill="none">
      <Defs>
        <LinearGradient id="logoGrad" x1="0" y1="0" x2="64" y2="64">
          <Stop offset="0" stopColor="#8b5cf6" />
          <Stop offset="0.5" stopColor="#a78bfa" />
          <Stop offset="1" stopColor="#c4b5fd" />
        </LinearGradient>
        <LinearGradient id="sparkGrad" x1="0" y1="0" x2="64" y2="64">
          <Stop offset="0" stopColor="#ffd43b" />
          <Stop offset="1" stopColor="#ff922b" />
        </LinearGradient>
      </Defs>

      {/* Glow ring */}
      <AnimatedCircle
        cx="32"
        cy="32"
        fill="#8b5cf6"
        animatedProps={animatedProps}
      />

      {/* Hanger shape */}
      <Path
        d="M32 12 L32 20 M20 28 Q20 20 32 20 Q44 20 44 28 L46 40 Q46 44 42 44 L22 44 Q18 44 18 40 Z"
        stroke="url(#logoGrad)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />

      {/* Hook */}
      <Path
        d="M32 12 Q28 8 32 6 Q36 8 32 12"
        stroke="url(#logoGrad)"
        strokeWidth="2"
        fill="none"
      />

      {/* AI sparkle */}
      <Path
        d="M48 14 L50 18 L54 16 L52 20 L56 22 L52 24 L54 28 L50 26 L48 30 L46 26 L42 28 L44 24 L40 22 L44 20 L42 16 L46 18 Z"
        fill="url(#sparkGrad)"
        opacity="0.9"
      />

      {/* Garment lines */}
      <Path
        d="M26 32 L38 32 M24 36 L40 36 M26 40 L38 40"
        stroke="#c4b5fd"
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity="0.5"
      />
    </Svg>
  );
}
```

### `src/components/svg/HangerIcon.tsx`

```tsx
import React from "react";
import Svg, { Path, Defs, LinearGradient, Stop } from "react-native-svg";

interface Props {
  size?: number;
  color?: string;
}

export function HangerIcon({ size = 24, color = "#a78bfa" }: Props) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Path
        d="M12 3C12 3 10 4.5 10 6C10 7.5 12 8 12 8L3.5 15.5C2.5 16.3 3 18 4.3 18H19.7C21 18 21.5 16.3 20.5 15.5L12 8"
        stroke={color}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <Path
        d="M8 21H16"
        stroke={color}
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </Svg>
  );
}
```

### `src/components/svg/SparkleIcon.tsx`

```tsx
import React, { useEffect } from "react";
import Svg, { Path } from "react-native-svg";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
} from "react-native-reanimated";

interface Props {
  size?: number;
  color?: string;
  animated?: boolean;
}

export function SparkleIcon({ size = 20, color = "#ffd43b", animated = false }: Props) {
  const rotation = useSharedValue(0);
  const scale = useSharedValue(1);

  useEffect(() => {
    if (animated) {
      rotation.value = withRepeat(
        withTiming(360, { duration: 4000 }),
        -1,
        false
      );
      scale.value = withRepeat(
        withSequence(
          withTiming(1.2, { duration: 1000 }),
          withTiming(0.9, { duration: 1000 })
        ),
        -1,
        true
      );
    }
  }, [animated]);

  const animStyle = useAnimatedStyle(() => ({
    transform: [
      { rotate: `${rotation.value}deg` },
      { scale: scale.value },
    ],
  }));

  return (
    <Animated.View style={animated ? animStyle : undefined}>
      <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <Path
          d="M12 2L13.5 8.5L20 7L15 12L20 17L13.5 15.5L12 22L10.5 15.5L4 17L9 12L4 7L10.5 8.5L12 2Z"
          fill={color}
          opacity="0.9"
        />
      </Svg>
    </Animated.View>
  );
}
```

### `src/components/svg/WardrobeIllustration.tsx`

```tsx
import React from "react";
import Svg, {
  Path, Rect, Circle, Line, Defs,
  LinearGradient, Stop, G,
} from "react-native-svg";

interface Props {
  width?: number;
  height?: number;
}

export function WardrobeIllustration({ width = 280, height = 240 }: Props) {
  return (
    <Svg width={width} height={height} viewBox="0 0 280 240" fill="none">
      <Defs>
        <LinearGradient id="wardBg" x1="0" y1="0" x2="280" y2="240">
          <Stop offset="0" stopColor="#1a1a24" />
          <Stop offset="1" stopColor="#24243a" />
        </LinearGradient>
        <LinearGradient id="wardAccent" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#8b5cf6" />
          <Stop offset="1" stopColor="#6d28d9" />
        </LinearGradient>
        <LinearGradient id="shirt1" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#4dabf7" />
          <Stop offset="1" stopColor="#339af0" />
        </LinearGradient>
        <LinearGradient id="shirt2" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#ff6b6b" />
          <Stop offset="1" stopColor="#f06595" />
        </LinearGradient>
        <LinearGradient id="shirt3" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#51cf66" />
          <Stop offset="1" stopColor="#40c057" />
        </LinearGradient>
      </Defs>

      {/* Background glow */}
      <Circle cx="140" cy="120" r="100" fill="#8b5cf6" opacity="0.06" />
      <Circle cx="140" cy="120" r="60" fill="#8b5cf6" opacity="0.08" />

      {/* Wardrobe body */}
      <Rect x="50" y="40" width="180" height="170" rx="12" fill="url(#wardBg)" stroke="#3b3b5c" strokeWidth="1.5" />

      {/* Center divider */}
      <Line x1="140" y1="50" x2="140" y2="200" stroke="#3b3b5c" strokeWidth="1" />

      {/* Handles */}
      <Rect x="128" y="110" width="4" height="20" rx="2" fill="#8b5cf6" opacity="0.8" />
      <Rect x="148" y="110" width="4" height="20" rx="2" fill="#8b5cf6" opacity="0.8" />

      {/* Hanging rod — left */}
      <Line x1="62" y1="60" x2="134" y2="60" stroke="#555" strokeWidth="2" strokeLinecap="round" />

      {/* Hanging rod — right */}
      <Line x1="146" y1="60" x2="218" y2="60" stroke="#555" strokeWidth="2" strokeLinecap="round" />

      {/* Hanger + shirt 1 (blue) */}
      <G>
        <Path d="M80 60 L80 65 L70 72 Q68 73 68 75 L68 100 Q68 102 70 102 L90 102 Q92 102 92 100 L92 75 Q92 73 90 72 L80 65" stroke="#888" strokeWidth="1.2" fill="url(#shirt1)" />
        <Path d="M80 60 Q78 57 80 55 Q82 57 80 60" stroke="#888" strokeWidth="1" fill="none" />
      </G>

      {/* Hanger + shirt 2 (coral) */}
      <G>
        <Path d="M106 60 L106 65 L96 72 Q94 73 94 75 L94 105 Q94 107 96 107 L116 107 Q118 107 118 105 L118 75 Q118 73 116 72 L106 65" stroke="#888" strokeWidth="1.2" fill="url(#shirt2)" />
        <Path d="M106 60 Q104 57 106 55 Q108 57 106 60" stroke="#888" strokeWidth="1" fill="none" />
      </G>

      {/* Hanger + shirt 3 (green) — right side */}
      <G>
        <Path d="M170 60 L170 65 L160 72 Q158 73 158 75 L158 95 Q158 97 160 97 L180 97 Q182 97 182 95 L182 75 Q182 73 180 72 L170 65" stroke="#888" strokeWidth="1.2" fill="url(#shirt3)" />
        <Path d="M170 60 Q168 57 170 55 Q172 57 170 60" stroke="#888" strokeWidth="1" fill="none" />
      </G>

      {/* Folded items on shelf — right bottom */}
      <Rect x="152" y="150" width="60" height="12" rx="3" fill="#4dabf7" opacity="0.4" />
      <Rect x="152" y="165" width="60" height="12" rx="3" fill="#ffd43b" opacity="0.3" />
      <Rect x="152" y="180" width="60" height="12" rx="3" fill="#ff6b6b" opacity="0.3" />

      {/* Shoes — left bottom */}
      <Circle cx="72" cy="190" r="8" fill="#3b3b5c" />
      <Circle cx="92" cy="190" r="8" fill="#3b3b5c" />

      {/* AI sparkle */}
      <Path
        d="M240 30L242 36L248 34L245 38L250 40L245 42L248 46L242 44L240 50L238 44L232 46L235 42L230 40L235 38L232 34L238 36Z"
        fill="#ffd43b"
        opacity="0.7"
      />
      <Path
        d="M46 180L47.5 183L51 182L49 185L52 186L49 187L51 190L47.5 189L46 192L44.5 189L41 190L43 187L40 186L43 185L41 182L44.5 183Z"
        fill="#a78bfa"
        opacity="0.5"
      />
    </Svg>
  );
}
```

### `src/components/svg/AnalyzingWave.tsx`

```tsx
import React, { useEffect } from "react";
import Svg, { Path, Defs, LinearGradient, Stop } from "react-native-svg";
import Animated, {
  useSharedValue,
  useAnimatedProps,
  withRepeat,
  withTiming,
  Easing,
  interpolate,
} from "react-native-reanimated";

const AnimatedPath = Animated.createAnimatedComponent(Path);

interface Props {
  width?: number;
  height?: number;
}

export function AnalyzingWave({ width = 320, height = 80 }: Props) {
  const progress = useSharedValue(0);

  useEffect(() => {
    progress.value = withRepeat(
      withTiming(1, { duration: 3000, easing: Easing.linear }),
      -1,
      false
    );
  }, []);

  const animatedProps = useAnimatedProps(() => {
    const shift = interpolate(progress.value, [0, 1], [0, 60]);
    return {
      d: `M0,40 Q${40 + shift},10 ${80 + shift},40 T${160 + shift},40 T${240 + shift},40 T${320 + shift},40 L320,80 L0,80 Z`,
    };
  });

  return (
    <Svg width={width} height={height} viewBox="0 0 320 80">
      <Defs>
        <LinearGradient id="waveGrad" x1="0" y1="0" x2="320" y2="0">
          <Stop offset="0" stopColor="#8b5cf6" stopOpacity="0.3" />
          <Stop offset="0.5" stopColor="#a78bfa" stopOpacity="0.5" />
          <Stop offset="1" stopColor="#8b5cf6" stopOpacity="0.3" />
        </LinearGradient>
      </Defs>
      <AnimatedPath animatedProps={animatedProps} fill="url(#waveGrad)" />
    </Svg>
  );
}
```

---

## 8. Animation System

### Core Animation Patterns

```typescript
// src/utils/animations.ts
import {
  withSpring,
  withTiming,
  withDelay,
  withSequence,
  Easing,
  type WithSpringConfig,
} from "react-native-reanimated";

/** Snappy spring for cards and buttons */
export const SPRING_SNAPPY: WithSpringConfig = {
  damping: 15,
  stiffness: 150,
  mass: 0.8,
};

/** Bouncy spring for celebrations */
export const SPRING_BOUNCY: WithSpringConfig = {
  damping: 8,
  stiffness: 120,
  mass: 1,
};

/** Gentle spring for layout shifts */
export const SPRING_GENTLE: WithSpringConfig = {
  damping: 20,
  stiffness: 90,
  mass: 1,
};

/** Smooth ease-out for fades */
export const fadeIn = (delay = 0) =>
  withDelay(delay, withTiming(1, { duration: 400, easing: Easing.out(Easing.cubic) }));

/** Staggered list entry — call per item with index */
export const staggeredEntry = (index: number) => ({
  opacity: withDelay(index * 80, withTiming(1, { duration: 350 })),
  translateY: withDelay(
    index * 80,
    withSpring(0, SPRING_SNAPPY)
  ),
});
```

### Animated Entry Wrapper Component

```tsx
// src/components/ui/AnimatedEntry.tsx
import React, { useEffect } from "react";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withDelay,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { SPRING_SNAPPY } from "../../utils/animations";

interface Props {
  children: React.ReactNode;
  index?: number;
  delay?: number;
  direction?: "up" | "down" | "left" | "right";
}

export function AnimatedEntry({
  children,
  index = 0,
  delay = 0,
  direction = "up",
}: Props) {
  const opacity = useSharedValue(0);
  const translate = useSharedValue(direction === "up" || direction === "left" ? 30 : -30);

  useEffect(() => {
    const totalDelay = delay + index * 100;
    opacity.value = withDelay(totalDelay, withTiming(1, { duration: 400 }));
    translate.value = withDelay(totalDelay, withSpring(0, SPRING_SNAPPY));
  }, []);

  const style = useAnimatedStyle(() => {
    const isVertical = direction === "up" || direction === "down";
    return {
      opacity: opacity.value,
      transform: [
        isVertical
          ? { translateY: translate.value }
          : { translateX: translate.value },
      ],
    };
  });

  return <Animated.View style={style}>{children}</Animated.View>;
}
```

### Progress Ring Component

```tsx
// src/components/ui/ProgressRing.tsx
import React, { useEffect } from "react";
import { View } from "react-native";
import Svg, { Circle, Defs, LinearGradient, Stop } from "react-native-svg";
import Animated, {
  useSharedValue,
  useAnimatedProps,
  withTiming,
  Easing,
} from "react-native-reanimated";

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

interface Props {
  size?: number;
  strokeWidth?: number;
  progress: number; // 0 to 1
  children?: React.ReactNode;
}

export function ProgressRing({
  size = 120,
  strokeWidth = 6,
  progress,
  children,
}: Props) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const animatedProgress = useSharedValue(0);

  useEffect(() => {
    animatedProgress.value = withTiming(progress, {
      duration: 800,
      easing: Easing.out(Easing.cubic),
    });
  }, [progress]);

  const animatedProps = useAnimatedProps(() => ({
    strokeDashoffset: circumference * (1 - animatedProgress.value),
  }));

  return (
    <View style={{ width: size, height: size, alignItems: "center", justifyContent: "center" }}>
      <Svg width={size} height={size} style={{ position: "absolute" }}>
        <Defs>
          <LinearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
            <Stop offset="0" stopColor="#8b5cf6" />
            <Stop offset="1" stopColor="#c4b5fd" />
          </LinearGradient>
        </Defs>
        {/* Background track */}
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="#24243a"
          strokeWidth={strokeWidth}
          fill="none"
        />
        {/* Animated progress */}
        <AnimatedCircle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="url(#ringGrad)"
          strokeWidth={strokeWidth}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          animatedProps={animatedProps}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </Svg>
      {children}
    </View>
  );
}
```

---

## 9. Typography & Design Tokens

### `src/theme/tokens.ts`

```typescript
/** Synclook design tokens — single source of truth */

export const colors = {
  brand: {
    50: "#f5f3ff", 100: "#ede9fe", 200: "#ddd6fe",
    300: "#c4b5fd", 400: "#a78bfa", 500: "#8b5cf6",
    600: "#7c3aed", 700: "#6d28d9", 800: "#5b21b6",
    900: "#4c1d95",
  },
  surface: {
    primary: "#0f0f14",   // App background
    secondary: "#1a1a24", // Cards
    tertiary: "#24243a",  // Elevated cards / inputs
    elevated: "#2a2a40",  // Modals
  },
  accent: {
    coral: "#ff6b6b",
    mint: "#51cf66",
    sky: "#4dabf7",
    gold: "#ffd43b",
    violet: "#9775fa",
  },
  text: {
    primary: "#f8fafc",
    secondary: "#94a3b8",
    tertiary: "#64748b",
    inverse: "#0f0f14",
  },
  semantic: {
    success: "#51cf66",
    warning: "#ffd43b",
    error: "#ff6b6b",
    info: "#4dabf7",
  },
} as const;

export const typography = {
  /** Inter — body text, labels, captions */
  body: {
    xs:   { fontFamily: "Inter_400Regular", fontSize: 11, lineHeight: 16 },
    sm:   { fontFamily: "Inter_400Regular", fontSize: 13, lineHeight: 18 },
    md:   { fontFamily: "Inter_400Regular", fontSize: 15, lineHeight: 22 },
    lg:   { fontFamily: "Inter_500Medium",  fontSize: 17, lineHeight: 24 },
  },
  /** Inter Semi/Bold — labels, buttons */
  label: {
    sm:   { fontFamily: "Inter_600SemiBold", fontSize: 12, lineHeight: 16, letterSpacing: 0.5 },
    md:   { fontFamily: "Inter_600SemiBold", fontSize: 14, lineHeight: 20 },
    lg:   { fontFamily: "Inter_700Bold",     fontSize: 16, lineHeight: 22 },
  },
  /** Space Grotesk — headlines */
  heading: {
    sm:   { fontFamily: "SpaceGrotesk_700Bold", fontSize: 20, lineHeight: 26 },
    md:   { fontFamily: "SpaceGrotesk_700Bold", fontSize: 24, lineHeight: 30 },
    lg:   { fontFamily: "SpaceGrotesk_700Bold", fontSize: 32, lineHeight: 40 },
    xl:   { fontFamily: "SpaceGrotesk_700Bold", fontSize: 40, lineHeight: 48 },
  },
} as const;

export const spacing = {
  xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48,
} as const;

export const radius = {
  sm: 8, md: 12, lg: 16, xl: 24, full: 9999,
} as const;

export const shadow = {
  sm: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 4,
    elevation: 2,
  },
  md: {
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 4,
  },
  lg: {
    shadowColor: "#8b5cf6",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.25,
    shadowRadius: 16,
    elevation: 8,
  },
} as const;

/** Map clothing color names to hex for UI display */
export const clothingColorMap: Record<string, string> = {
  black: "#1a1a2e",  white: "#f8f9fa",  red: "#e03131",
  blue: "#4dabf7",   navy: "#1c3879",   green: "#40c057",
  yellow: "#ffd43b",  orange: "#ff922b",  pink: "#f06595",
  purple: "#9775fa",  brown: "#8B4513",  grey: "#868e96",
  beige: "#d4c5a9",  cream: "#fffdd0",  maroon: "#800000",
  olive: "#6b8e23",  teal: "#20c997",   other: "#868e96",
};
```

---

## 10. Responsive Layout System

### `src/utils/responsive.ts`

```typescript
import { Dimensions, PixelRatio, Platform } from "react-native";

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get("window");

// Base design dimensions (iPhone 14 Pro)
const BASE_WIDTH = 393;
const BASE_HEIGHT = 852;

/**
 * Scale a value based on screen width.
 * E.g., wp(50) = 50% of screen width.
 */
export function wp(percentage: number): number {
  return PixelRatio.roundToNearestPixel((SCREEN_WIDTH * percentage) / 100);
}

/**
 * Scale a value based on screen height.
 */
export function hp(percentage: number): number {
  return PixelRatio.roundToNearestPixel((SCREEN_HEIGHT * percentage) / 100);
}

/**
 * Scale a fixed pixel value relative to base design width.
 * Keeps proportions consistent across device sizes.
 */
export function scale(size: number): number {
  return PixelRatio.roundToNearestPixel(
    (SCREEN_WIDTH / BASE_WIDTH) * size
  );
}

/**
 * Moderate scale — less aggressive than full scale.
 * Good for font sizes and spacing.
 */
export function moderateScale(size: number, factor = 0.5): number {
  return PixelRatio.roundToNearestPixel(
    size + (scale(size) - size) * factor
  );
}

/** Device size categories */
export type DeviceSize = "small" | "medium" | "large" | "tablet";

export function getDeviceSize(): DeviceSize {
  if (SCREEN_WIDTH < 360) return "small";      // iPhone SE, small Androids
  if (SCREEN_WIDTH < 400) return "medium";      // Standard phones
  if (SCREEN_WIDTH < 768) return "large";       // Large phones (Pro Max)
  return "tablet";                               // iPads & tablets
}

/** Number of outfit card columns based on screen */
export function getCardColumns(): number {
  const device = getDeviceSize();
  switch (device) {
    case "small":
    case "medium": return 1;
    case "large": return 1;
    case "tablet": return 2;
  }
}

/** Card width based on screen with margins */
export function getCardWidth(padding = 16): number {
  const cols = getCardColumns();
  const totalPadding = padding * 2 + (cols - 1) * padding;
  return (SCREEN_WIDTH - totalPadding) / cols;
}

export { SCREEN_WIDTH, SCREEN_HEIGHT };
```

---

## 11. State Management

### `src/store/useAppStore.ts`

```typescript
import { create } from "zustand";
import type { AnalysisResponse, Recommendation } from "../types/api";

interface AppState {
  // User
  userId: string | null;
  setUserId: (id: string) => void;

  // Analysis
  currentImage: string | null;
  setCurrentImage: (uri: string | null) => void;

  lastAnalysis: AnalysisResponse | null;
  setLastAnalysis: (result: AnalysisResponse | null) => void;

  // History
  analysisHistory: AnalysisResponse[];
  addToHistory: (result: AnalysisResponse) => void;

  // Feedback
  feedbackGiven: Record<string, "like" | "dislike">;
  setFeedback: (recommendationId: string, type: "like" | "dislike") => void;

  // UI
  theme: "dark" | "light";
  toggleTheme: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  userId: null,
  setUserId: (id) => set({ userId: id }),

  currentImage: null,
  setCurrentImage: (uri) => set({ currentImage: uri }),

  lastAnalysis: null,
  setLastAnalysis: (result) =>
    set((state) => ({
      lastAnalysis: result,
      analysisHistory: result
        ? [result, ...state.analysisHistory.slice(0, 19)]
        : state.analysisHistory,
    })),

  analysisHistory: [],
  addToHistory: (result) =>
    set((state) => ({
      analysisHistory: [result, ...state.analysisHistory.slice(0, 19)],
    })),

  feedbackGiven: {},
  setFeedback: (id, type) =>
    set((state) => ({
      feedbackGiven: { ...state.feedbackGiven, [id]: type },
    })),

  theme: "dark",
  toggleTheme: () =>
    set((state) => ({
      theme: state.theme === "dark" ? "light" : "dark",
    })),
}));
```

---

## 12. Complete Component Code

### Home Screen

```tsx
// src/screens/HomeScreen.tsx
import React, { useCallback } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as ImagePicker from "expo-image-picker";
import * as Haptics from "expo-haptics";
import { useNavigation } from "@react-navigation/native";

import { LogoSvg } from "../components/svg/LogoSvg";
import { WardrobeIllustration } from "../components/svg/WardrobeIllustration";
import { SparkleIcon } from "../components/svg/SparkleIcon";
import { AnimatedEntry } from "../components/ui/AnimatedEntry";
import { useAppStore } from "../store/useAppStore";
import { colors, typography, spacing, radius, shadow } from "../theme/tokens";
import { scale, wp, hp } from "../utils/responsive";

export default function HomeScreen() {
  const navigation = useNavigation<any>();
  const setCurrentImage = useAppStore((s) => s.setCurrentImage);

  const pickImage = useCallback(async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true,
      aspect: [3, 4],
      quality: 0.8,
    });

    if (!result.canceled && result.assets[0]) {
      setCurrentImage(result.assets[0].uri);
      navigation.navigate("Analysis");
    }
  }, []);

  const takePhoto = useCallback(async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== "granted") return;

    const result = await ImagePicker.launchCameraAsync({
      allowsEditing: true,
      aspect: [3, 4],
      quality: 0.8,
    });

    if (!result.canceled && result.assets[0]) {
      setCurrentImage(result.assets[0].uri);
      navigation.navigate("Analysis");
    }
  }, []);

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <AnimatedEntry index={0}>
          <View style={styles.header}>
            <LogoSvg size={scale(44)} />
            <View style={{ marginLeft: spacing.md }}>
              <Text style={styles.title}>Synclook</Text>
              <Text style={styles.subtitle}>AI Fashion Agent</Text>
            </View>
          </View>
        </AnimatedEntry>

        {/* Hero Illustration */}
        <AnimatedEntry index={1}>
          <View style={styles.heroContainer}>
            <WardrobeIllustration width={wp(75)} height={hp(28)} />
          </View>
        </AnimatedEntry>

        {/* CTA Section */}
        <AnimatedEntry index={2}>
          <View style={styles.ctaSection}>
            <View style={styles.ctaRow}>
              <SparkleIcon size={20} color={colors.accent.gold} animated />
              <Text style={styles.ctaHeadline}>What are you wearing?</Text>
            </View>
            <Text style={styles.ctaBody}>
              Upload a photo of your clothing and our AI agents will craft
              the perfect outfit recommendations for you.
            </Text>
          </View>
        </AnimatedEntry>

        {/* Action Buttons */}
        <AnimatedEntry index={3}>
          <TouchableOpacity
            style={styles.primaryButton}
            onPress={pickImage}
            activeOpacity={0.85}
          >
            <Text style={styles.primaryButtonText}>📸  Choose from Gallery</Text>
          </TouchableOpacity>
        </AnimatedEntry>

        <AnimatedEntry index={4}>
          <TouchableOpacity
            style={styles.secondaryButton}
            onPress={takePhoto}
            activeOpacity={0.85}
          >
            <Text style={styles.secondaryButtonText}>📷  Take a Photo</Text>
          </TouchableOpacity>
        </AnimatedEntry>

        {/* Footer note */}
        <AnimatedEntry index={5}>
          <Text style={styles.footer}>
            Powered by CLIP + BLIP vision models{"\n"}
            Rule-based styling intelligence
          </Text>
        </AnimatedEntry>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface.primary,
  },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.xl,
  },
  title: {
    ...typography.heading.md,
    color: colors.text.primary,
  },
  subtitle: {
    ...typography.body.sm,
    color: colors.brand[400],
    marginTop: 2,
  },
  heroContainer: {
    alignItems: "center",
    marginBottom: spacing.xl,
  },
  ctaSection: {
    backgroundColor: colors.surface.secondary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.lg,
    borderWidth: 1,
    borderColor: colors.surface.tertiary,
  },
  ctaRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  ctaHeadline: {
    ...typography.heading.sm,
    color: colors.text.primary,
    marginLeft: spacing.sm,
  },
  ctaBody: {
    ...typography.body.md,
    color: colors.text.secondary,
  },
  primaryButton: {
    backgroundColor: colors.brand[600],
    borderRadius: radius.xl,
    paddingVertical: spacing.md + 2,
    alignItems: "center",
    marginBottom: spacing.md,
    ...shadow.lg,
  },
  primaryButtonText: {
    ...typography.label.lg,
    color: colors.text.primary,
  },
  secondaryButton: {
    backgroundColor: colors.surface.tertiary,
    borderRadius: radius.xl,
    paddingVertical: spacing.md + 2,
    alignItems: "center",
    marginBottom: spacing.xl,
    borderWidth: 1,
    borderColor: colors.brand[700],
  },
  secondaryButtonText: {
    ...typography.label.lg,
    color: colors.brand[300],
  },
  footer: {
    ...typography.body.xs,
    color: colors.text.tertiary,
    textAlign: "center",
    lineHeight: 18,
  },
});
```

### Analysis Screen (SSE Streaming)

```tsx
// src/screens/AnalysisScreen.tsx
import React, { useEffect } from "react";
import { View, Text, StyleSheet, Image } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withRepeat,
  withTiming,
  Easing,
} from "react-native-reanimated";
import { useNavigation } from "@react-navigation/native";

import { useAnalysis } from "../hooks/useAnalysis";
import { useAppStore } from "../store/useAppStore";
import { ProgressRing } from "../components/ui/ProgressRing";
import { SparkleIcon } from "../components/svg/SparkleIcon";
import { AnimatedEntry } from "../components/ui/AnimatedEntry";
import { colors, typography, spacing, radius } from "../theme/tokens";
import { wp, hp, scale } from "../utils/responsive";

const STAGE_MAP: Record<string, { label: string; icon: string }> = {
  vision: { label: "Analyzing your clothing", icon: "👁️" },
  styling: { label: "Matching complementary styles", icon: "🎨" },
  recommendation: { label: "Crafting outfit suggestions", icon: "✨" },
};

export default function AnalysisScreen() {
  const navigation = useNavigation<any>();
  const currentImage = useAppStore((s) => s.currentImage);
  const setLastAnalysis = useAppStore((s) => s.setLastAnalysis);
  const { status, stages, result, error, elapsed, analyze } = useAnalysis();

  // Start analysis on mount
  useEffect(() => {
    if (currentImage) {
      analyze(currentImage);
    }
  }, [currentImage]);

  // Navigate to results when done
  useEffect(() => {
    if (status === "done" && result) {
      setLastAnalysis(result);
      const timer = setTimeout(() => {
        navigation.replace("Results");
      }, 800); // Brief pause for celebration animation
      return () => clearTimeout(timer);
    }
  }, [status, result]);

  const completedCount = stages.filter((s) => s.status === "done").length;
  const progress = stages.length > 0 ? completedCount / stages.length : 0;

  // Pulsing glow animation
  const glowOpacity = useSharedValue(0.3);
  useEffect(() => {
    glowOpacity.value = withRepeat(
      withTiming(0.6, { duration: 1500, easing: Easing.inOut(Easing.ease) }),
      -1,
      true
    );
  }, []);
  const glowStyle = useAnimatedStyle(() => ({
    opacity: glowOpacity.value,
  }));

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        {/* Image preview with glow */}
        <AnimatedEntry index={0}>
          <View style={styles.imageContainer}>
            <Animated.View style={[styles.imageGlow, glowStyle]} />
            {currentImage && (
              <Image
                source={{ uri: currentImage }}
                style={styles.image}
                resizeMode="cover"
              />
            )}
          </View>
        </AnimatedEntry>

        {/* Progress ring */}
        <AnimatedEntry index={1}>
          <View style={styles.progressContainer}>
            <ProgressRing size={scale(100)} progress={progress}>
              <Text style={styles.progressText}>
                {Math.round(progress * 100)}%
              </Text>
            </ProgressRing>
          </View>
        </AnimatedEntry>

        {/* Stage indicators */}
        <View style={styles.stagesContainer}>
          {stages.map((stage, index) => (
            <AnimatedEntry key={stage.stage} index={index + 2}>
              <View
                style={[
                  styles.stageRow,
                  stage.status === "active" && styles.stageActive,
                  stage.status === "done" && styles.stageDone,
                ]}
              >
                <Text style={styles.stageIcon}>
                  {stage.status === "done"
                    ? "✅"
                    : stage.status === "active"
                    ? STAGE_MAP[stage.stage]?.icon || "⏳"
                    : "⏸️"}
                </Text>
                <View style={{ flex: 1, marginLeft: spacing.md }}>
                  <Text
                    style={[
                      styles.stageLabel,
                      stage.status === "active" && styles.stageLabelActive,
                      stage.status === "done" && styles.stageLabelDone,
                    ]}
                  >
                    {STAGE_MAP[stage.stage]?.label || stage.stage}
                  </Text>
                  {stage.status === "active" && (
                    <View style={styles.activeIndicator}>
                      <SparkleIcon size={12} color={colors.accent.gold} animated />
                      <Text style={styles.activeText}>Processing...</Text>
                    </View>
                  )}
                </View>
              </View>
            </AnimatedEntry>
          ))}
        </View>

        {/* Error state */}
        {error && (
          <AnimatedEntry>
            <View style={styles.errorBox}>
              <Text style={styles.errorText}>⚠️ {error}</Text>
            </View>
          </AnimatedEntry>
        )}

        {/* Done celebration */}
        {status === "done" && (
          <AnimatedEntry>
            <Text style={styles.doneText}>
              ✨ Analysis complete in {elapsed.toFixed(1)}s
            </Text>
          </AnimatedEntry>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface.primary },
  content: { flex: 1, paddingHorizontal: spacing.lg, paddingTop: spacing.lg },
  imageContainer: {
    alignSelf: "center",
    width: wp(45),
    height: wp(60),
    borderRadius: radius.lg,
    overflow: "hidden",
    marginBottom: spacing.xl,
  },
  imageGlow: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: colors.brand[600],
    borderRadius: radius.lg,
    transform: [{ scale: 1.05 }],
  },
  image: {
    width: "100%",
    height: "100%",
    borderRadius: radius.lg,
  },
  progressContainer: {
    alignItems: "center",
    marginBottom: spacing.xl,
  },
  progressText: {
    ...typography.heading.sm,
    color: colors.brand[300],
  },
  stagesContainer: { gap: spacing.md },
  stageRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface.secondary,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.surface.tertiary,
  },
  stageActive: {
    borderColor: colors.brand[500],
    backgroundColor: colors.surface.tertiary,
  },
  stageDone: {
    borderColor: colors.accent.mint,
    opacity: 0.8,
  },
  stageIcon: { fontSize: scale(22) },
  stageLabel: {
    ...typography.label.md,
    color: colors.text.tertiary,
  },
  stageLabelActive: { color: colors.text.primary },
  stageLabelDone: { color: colors.accent.mint },
  activeIndicator: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 4,
  },
  activeText: {
    ...typography.body.xs,
    color: colors.accent.gold,
    marginLeft: 6,
  },
  errorBox: {
    backgroundColor: "rgba(255,107,107,0.1)",
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.lg,
    borderWidth: 1,
    borderColor: colors.accent.coral,
  },
  errorText: { ...typography.body.sm, color: colors.accent.coral },
  doneText: {
    ...typography.label.lg,
    color: colors.accent.mint,
    textAlign: "center",
    marginTop: spacing.xl,
  },
});
```

### Results Screen with Outfit Cards

```tsx
// src/screens/ResultsScreen.tsx
import React, { useCallback } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";

import { useAppStore } from "../store/useAppStore";
import { submitFeedback } from "../api/endpoints";
import { AnimatedEntry } from "../components/ui/AnimatedEntry";
import { SparkleIcon } from "../components/svg/SparkleIcon";
import { HangerIcon } from "../components/svg/HangerIcon";
import {
  colors,
  typography,
  spacing,
  radius,
  shadow,
  clothingColorMap,
} from "../theme/tokens";
import { wp, scale } from "../utils/responsive";
import type { Recommendation, RecommendationItem } from "../types/api";

function ColorDot({ colorName }: { colorName: string }) {
  const hex = clothingColorMap[colorName] || colors.text.tertiary;
  return (
    <View
      style={[
        styles.colorDot,
        { backgroundColor: hex },
        colorName === "white" && { borderWidth: 1, borderColor: "#555" },
      ]}
    />
  );
}

function ClothingChip({ item }: { item: RecommendationItem }) {
  return (
    <View style={styles.chip}>
      <ColorDot colorName={item.color} />
      <View style={{ marginLeft: spacing.sm, flex: 1 }}>
        <Text style={styles.chipTitle}>
          {item.color} {item.item_type}
        </Text>
        <Text style={styles.chipReason} numberOfLines={2}>
          {item.reason}
        </Text>
      </View>
    </View>
  );
}

function OutfitCard({
  recommendation,
  index,
}: {
  recommendation: Recommendation;
  index: number;
}) {
  const { feedbackGiven, setFeedback } = useAppStore();
  const lastAnalysis = useAppStore((s) => s.lastAnalysis);
  const given = feedbackGiven[recommendation.id];

  const handleFeedback = useCallback(
    async (type: "like" | "dislike") => {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      setFeedback(recommendation.id, type);
      try {
        await submitFeedback({
          request_id: lastAnalysis?.request_id || "",
          recommendation_id: recommendation.id,
          feedback: type,
          user_id: useAppStore.getState().userId || undefined,
        });
      } catch {
        // Feedback is best-effort
      }
    },
    [recommendation.id, lastAnalysis]
  );

  return (
    <AnimatedEntry index={index} direction="up">
      <View style={styles.card}>
        {/* Card header */}
        <View style={styles.cardHeader}>
          <HangerIcon size={scale(20)} color={colors.brand[400]} />
          <Text style={styles.cardTitle}>Outfit {index + 1}</Text>
          <View style={styles.confidenceBadge}>
            <Text style={styles.confidenceText}>
              {Math.round(recommendation.confidence * 100)}% match
            </Text>
          </View>
        </View>

        {/* Style tags */}
        <View style={styles.tagsRow}>
          {recommendation.style_tags
            .filter((t, i, a) => a.indexOf(t) === i)
            .slice(0, 3)
            .map((tag) => (
              <View key={tag} style={styles.tag}>
                <Text style={styles.tagText}>{tag}</Text>
              </View>
            ))}
        </View>

        {/* Explanation */}
        <Text style={styles.explanation}>
          {recommendation.overall_explanation}
        </Text>

        {/* Items */}
        <View style={styles.itemsContainer}>
          {recommendation.items.map((item, i) => (
            <ClothingChip key={i} item={item} />
          ))}
        </View>

        {/* Feedback buttons */}
        <View style={styles.feedbackRow}>
          <TouchableOpacity
            style={[
              styles.feedbackBtn,
              given === "like" && styles.feedbackBtnActive,
            ]}
            onPress={() => handleFeedback("like")}
            disabled={!!given}
          >
            <Text style={styles.feedbackEmoji}>👍</Text>
            <Text
              style={[
                styles.feedbackLabel,
                given === "like" && { color: colors.accent.mint },
              ]}
            >
              Love it
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.feedbackBtn,
              given === "dislike" && styles.feedbackBtnActive,
            ]}
            onPress={() => handleFeedback("dislike")}
            disabled={!!given}
          >
            <Text style={styles.feedbackEmoji}>👎</Text>
            <Text
              style={[
                styles.feedbackLabel,
                given === "dislike" && { color: colors.accent.coral },
              ]}
            >
              Not for me
            </Text>
          </TouchableOpacity>
        </View>
      </View>
    </AnimatedEntry>
  );
}

export default function ResultsScreen() {
  const lastAnalysis = useAppStore((s) => s.lastAnalysis);
  const navigation = useNavigation<any>();

  if (!lastAnalysis) return null;

  const attrs = lastAnalysis.detected_attributes;

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        {/* Detected attributes header */}
        <AnimatedEntry index={0}>
          <View style={styles.detectedSection}>
            <SparkleIcon size={18} color={colors.accent.gold} animated />
            <Text style={styles.detectedTitle}>We detected</Text>
          </View>
          <View style={styles.attributeRow}>
            <ColorDot colorName={attrs.primary_color} />
            <Text style={styles.attributeText}>
              {attrs.primary_color} {attrs.clothing_type} •{" "}
              {attrs.style} • {attrs.pattern}
            </Text>
          </View>
          {attrs.description ? (
            <Text style={styles.captionText}>"{attrs.description}"</Text>
          ) : null}
        </AnimatedEntry>

        {/* Recommendations */}
        <AnimatedEntry index={1}>
          <Text style={styles.sectionTitle}>
            Recommended Outfits ({lastAnalysis.recommendations.length})
          </Text>
        </AnimatedEntry>

        {lastAnalysis.recommendations.map((rec, i) => (
          <OutfitCard key={rec.id} recommendation={rec} index={i + 2} />
        ))}

        {/* Try again */}
        <AnimatedEntry
          index={lastAnalysis.recommendations.length + 3}
        >
          <TouchableOpacity
            style={styles.tryAgainBtn}
            onPress={() => navigation.navigate("Home")}
            activeOpacity={0.85}
          >
            <Text style={styles.tryAgainText}>
              📸  Analyze Another Item
            </Text>
          </TouchableOpacity>
        </AnimatedEntry>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface.primary },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  detectedSection: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  detectedTitle: {
    ...typography.heading.sm,
    color: colors.text.primary,
    marginLeft: spacing.sm,
  },
  attributeRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.xs,
  },
  attributeText: {
    ...typography.label.md,
    color: colors.brand[300],
    marginLeft: spacing.sm,
    textTransform: "capitalize",
  },
  captionText: {
    ...typography.body.sm,
    color: colors.text.tertiary,
    fontStyle: "italic",
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    ...typography.heading.sm,
    color: colors.text.primary,
    marginBottom: spacing.md,
    marginTop: spacing.md,
  },
  card: {
    backgroundColor: colors.surface.secondary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.surface.tertiary,
    ...shadow.md,
  },
  cardHeader: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: spacing.md,
  },
  cardTitle: {
    ...typography.label.lg,
    color: colors.text.primary,
    marginLeft: spacing.sm,
    flex: 1,
  },
  confidenceBadge: {
    backgroundColor: colors.brand[900],
    borderRadius: radius.full,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: 3,
  },
  confidenceText: {
    ...typography.body.xs,
    color: colors.brand[300],
  },
  tagsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.xs,
    marginBottom: spacing.md,
  },
  tag: {
    backgroundColor: colors.surface.tertiary,
    borderRadius: radius.full,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: 3,
  },
  tagText: {
    ...typography.body.xs,
    color: colors.text.secondary,
    textTransform: "capitalize",
  },
  explanation: {
    ...typography.body.md,
    color: colors.text.secondary,
    marginBottom: spacing.md,
    lineHeight: 22,
  },
  itemsContainer: { gap: spacing.sm, marginBottom: spacing.md },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface.tertiary,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  chipTitle: {
    ...typography.label.md,
    color: colors.text.primary,
    textTransform: "capitalize",
  },
  chipReason: {
    ...typography.body.xs,
    color: colors.text.tertiary,
    marginTop: 2,
  },
  colorDot: {
    width: scale(18),
    height: scale(18),
    borderRadius: scale(9),
  },
  feedbackRow: {
    flexDirection: "row",
    gap: spacing.md,
  },
  feedbackBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface.tertiary,
    borderRadius: radius.md,
    paddingVertical: spacing.sm + 2,
    gap: spacing.xs,
  },
  feedbackBtnActive: {
    borderWidth: 1,
    borderColor: colors.brand[500],
  },
  feedbackEmoji: { fontSize: scale(16) },
  feedbackLabel: {
    ...typography.label.sm,
    color: colors.text.secondary,
  },
  tryAgainBtn: {
    backgroundColor: colors.brand[600],
    borderRadius: radius.xl,
    paddingVertical: spacing.md + 2,
    alignItems: "center",
    marginTop: spacing.lg,
    ...shadow.lg,
  },
  tryAgainText: {
    ...typography.label.lg,
    color: colors.text.primary,
  },
});
```

---

## 13. Testing & Debugging

### Connecting to Local Backend

```bash
# Find your local IP address
ifconfig | grep "inet " | grep -v 127.0.0.1

# Update src/api/client.ts with your local IP:
# const BASE_URL = "http://192.168.1.XXX:8000";

# Start the backend (from synclookai directory)
poetry run uvicorn main:app --host 0.0.0.0 --port 8000

# Start Expo
cd Synclook
npx expo start
```

### Debugging SSE Streams

```typescript
// Temporary: Add to src/api/sse.ts for debugging
const DEBUG_SSE = __DEV__;

function handleSSEEvent(event: string, data: any, callbacks: StreamCallbacks) {
  if (DEBUG_SSE) {
    console.log(`[SSE] ${event}:`, JSON.stringify(data).slice(0, 200));
  }
  // ... rest of handler
}
```

### Testing Without Backend

```typescript
// src/api/__mocks__/mockAnalysis.ts
export const MOCK_ANALYSIS = {
  request_id: "mock-123",
  detected_attributes: {
    clothing_type: "shirt",
    primary_color: "navy",
    pattern: "solid",
    style: "smart_casual",
    confidence: 0.85,
    description: "a navy blue dress shirt",
    secondary_color: null,
  },
  recommendations: [
    {
      id: "rec-1",
      items: [
        { item_type: "trousers", color: "white", style: "smart_casual",
          reason: "White trousers create a crisp contrast with navy." },
        { item_type: "blazer", color: "beige", style: "smart_casual",
          reason: "Beige blazer adds warmth to the navy foundation." },
      ],
      overall_explanation: "A refined smart-casual ensemble...",
      style_tags: ["smart_casual", "formal"],
      confidence: 0.9,
    },
  ],
  created_at: new Date().toISOString(),
};
```

### Backend API Quick Reference

| Endpoint | Method | Content-Type | Body | Returns |
|---|---|---|---|---|
| `/api/v1/health` | `GET` | — | — | `{ status, version }` |
| `/api/v1/analyze` | `POST` | `multipart/form-data` | `image` file + `user_id` query | `AnalysisResponse` JSON |
| `/api/v1/analyze/stream` | `POST` | `multipart/form-data` | `image` file + `user_id` query | SSE event stream |
| `/api/v1/feedback` | `POST` | `application/json` | `FeedbackRequest` body | `{ status, message }` |

### SSE Event Sequence

```
event: status     → { stage: "start", message: "Analysis started", request_id: "..." }
event: status     → { stage: "vision", message: "Analyzing image..." }
event: agent_done → { stage: "vision", message: "vision complete" }
event: status     → { stage: "styling", message: "Generating style matches..." }
event: agent_done → { stage: "styling", message: "styling complete" }
event: status     → { stage: "recommendation", message: "Building recommendations..." }
event: agent_done → { stage: "recommendation", message: "recommendation complete" }
event: result     → { request_id, detected_attributes, recommendations, errors }
event: done       → { elapsed_s: 15.2 }
```

---

## Design Checklist

- [x] **Dark mode** — deep purple/slate surfaces, high-contrast text
- [x] **Custom SVGs** — Logo, hanger, sparkle, wardrobe illustration, analyzing wave
- [x] **Animations** — Reanimated 3 springs, staggered entries, progress ring, pulsing glows
- [x] **Typography** — Space Grotesk for headlines, Inter for body, proper hierarchy
- [x] **Responsive** — `wp()`, `hp()`, `scale()` utilities, device-size breakpoints
- [x] **Haptic feedback** — Light/Medium impacts on interactions, success/error notifications
- [x] **SSE streaming** — Real-time pipeline progress with stage indicators
- [x] **Color mapping** — Clothing color names → visual dots with `clothingColorMap`
- [x] **Feedback loop** — Like/dislike buttons POST to backend, update Redis preferences
- [x] **Error states** — Graceful error display, retry capability
- [x] **Safe area** — Respects notches, home indicators on all devices
- [x] **Accessibility** — Proper text sizes, touch targets ≥ 44pt

---

*This guide pairs with the Synclook backend (Steps 1–11). All API contracts, event types, and schema shapes match the backend exactly.*
