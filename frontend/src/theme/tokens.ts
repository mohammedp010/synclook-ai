/** StyleForge design tokens — dark + purple AI-first palette */

export const colors = {
  brand: {
    50:  "#f5f3ff",
    100: "#ede9fe",
    200: "#ddd6fe",
    300: "#c4b5fd",
    400: "#a78bfa",
    500: "#8b5cf6",   // primary brand purple
    600: "#7c3aed",
    700: "#6d28d9",
    800: "#5b21b6",
    900: "#4c1d95",
  },
  surface: {
    primary:   "#0f0f14",   // deep dark background
    secondary: "#1a1a2e",   // card / elevated surfaces
    tertiary:  "#222238",   // subtle panel tint
    elevated:  "#2a2a40",   // popovers / modals
    border:    "#2e2e4a",   // subtle border
  },
  muted: {
    100: "#1e1e32",
    200: "#28283e",
    300: "#3a3a56",
    400: "#5a5a78",
    500: "#7a7a96",
  },
  text: {
    primary:   "#f8fafc",   // near-white
    secondary: "#94a3b8",   // muted slate
    tertiary:  "#64748b",   // dimmed
    inverse:   "#0f0f14",   // on light backgrounds
    onBrand:   "#ffffff",   // on purple fills
  },
  semantic: {
    success:   "#34d399",
    successBg: "#052e16",
    error:     "#f87171",
    errorBg:   "#450a0a",
    warning:   "#fbbf24",
    warningBg: "#451a03",
    info:      "#60a5fa",
    infoBg:    "#172554",
  },
  accent: {
    coral:  "#ff6b6b",
    mint:   "#51cf66",
    sky:    "#4dabf7",
    gold:   "#ffd43b",
    violet: "#9775fa",
  },
  /** Gradient color stops */
  gradient: {
    purple:    ["#8b5cf6", "#6d28d9"] as const,
    glow:      ["#a78bfa", "#7c3aed"] as const,
    shimmer:   ["#c4b5fd", "#8b5cf6", "#6d28d9"] as const,
    surface:   ["#1a1a2e", "#0f0f14"] as const,
  },
} as const;

export const typography = {
  /** Inter — body text, captions */
  body: {
    xs: { fontFamily: "Inter_400Regular", fontSize: 11, lineHeight: 16 },
    sm: { fontFamily: "Inter_400Regular", fontSize: 13, lineHeight: 18 },
    md: { fontFamily: "Inter_400Regular", fontSize: 15, lineHeight: 22 },
    lg: { fontFamily: "Inter_500Medium", fontSize: 17, lineHeight: 24 },
  },
  /** Inter Semi/Bold — labels, buttons */
  label: {
    sm: { fontFamily: "Inter_600SemiBold", fontSize: 12, lineHeight: 16, letterSpacing: 0.5 },
    md: { fontFamily: "Inter_600SemiBold", fontSize: 14, lineHeight: 20 },
    lg: { fontFamily: "Inter_700Bold", fontSize: 16, lineHeight: 22 },
  },
  /** Space Grotesk — headlines */
  heading: {
    sm: { fontFamily: "SpaceGrotesk_700Bold", fontSize: 20, lineHeight: 26 },
    md: { fontFamily: "SpaceGrotesk_700Bold", fontSize: 24, lineHeight: 30 },
    lg: { fontFamily: "SpaceGrotesk_700Bold", fontSize: 32, lineHeight: 40 },
    xl: { fontFamily: "SpaceGrotesk_700Bold", fontSize: 40, lineHeight: 48 },
  },
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  full: 9999,
} as const;

export const shadow = {
  sm: {
    shadowColor: "#8b5cf6",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 2,
  },
  md: {
    shadowColor: "#8b5cf6",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 4,
  },
  lg: {
    shadowColor: "#8b5cf6",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.25,
    shadowRadius: 24,
    elevation: 8,
  },
} as const;

/** Glassmorphism card styles */
export const glass = {
  card: {
    backgroundColor: "rgba(26, 26, 46, 0.7)",
    borderWidth: 1,
    borderColor: "rgba(139, 92, 246, 0.15)",
  },
  elevated: {
    backgroundColor: "rgba(42, 42, 64, 0.8)",
    borderWidth: 1,
    borderColor: "rgba(139, 92, 246, 0.2)",
  },
} as const;

/** Map clothing color names → hex for UI display */
export const clothingColorMap: Record<string, string> = {
  black: "#1e1e32",
  white: "#f8fafc",
  red: "#f87171",
  blue: "#60a5fa",
  navy: "#3b82f6",
  green: "#34d399",
  yellow: "#fbbf24",
  orange: "#fb923c",
  pink: "#f472b6",
  purple: "#a78bfa",
  brown: "#a0845c",
  grey: "#94a3b8",
  beige: "#d4c5a9",
  cream: "#fef3c7",
  maroon: "#dc2626",
  olive: "#84cc16",
  teal: "#2dd4bf",
  other: "#94a3b8",
};
