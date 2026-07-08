import { Dimensions, PixelRatio, Platform, type ViewStyle } from "react-native";

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get("window");

const BASE_WIDTH = 393;
const BASE_HEIGHT = 852;

/** Whether we're running in a web browser. */
export const isWeb = Platform.OS === "web";

/** Whether the viewport is wide enough for a desktop layout. */
export const isWideWeb = isWeb && SCREEN_WIDTH >= 900;

/** Max content width — wider on web, capped on mobile. */
const MAX_CONTENT_WIDTH = isWeb ? 960 : 600;

/** Scale a value based on screen width percentage. */
export function wp(percentage: number): number {
  if (isWeb) return (Math.min(SCREEN_WIDTH, 1440) * percentage) / 100;
  return PixelRatio.roundToNearestPixel((SCREEN_WIDTH * percentage) / 100);
}

/** Scale a value based on screen height percentage. */
export function hp(percentage: number): number {
  if (isWeb) return (Math.min(SCREEN_HEIGHT, 900) * percentage) / 100;
  return PixelRatio.roundToNearestPixel((SCREEN_HEIGHT * percentage) / 100);
}

/** Scale a fixed pixel value relative to base design width (393px). */
export function scale(size: number): number {
  if (isWeb) return size; // no scaling on web — CSS pixels are fine
  return PixelRatio.roundToNearestPixel((SCREEN_WIDTH / BASE_WIDTH) * size);
}

/** Moderate scale — less aggressive than full scale. Good for font sizes. */
export function moderateScale(size: number, factor = 0.5): number {
  if (isWeb) return size;
  return PixelRatio.roundToNearestPixel(size + (scale(size) - size) * factor);
}

export type DeviceSize = "small" | "medium" | "large" | "tablet" | "desktop";

export function getDeviceSize(): DeviceSize {
  if (isWeb && SCREEN_WIDTH >= 1200) return "desktop";
  if (SCREEN_WIDTH < 360) return "small";
  if (SCREEN_WIDTH < 400) return "medium";
  if (SCREEN_WIDTH < 768) return "large";
  return "tablet";
}

export function getCardColumns(): number {
  const device = getDeviceSize();
  switch (device) {
    case "small":
    case "medium":
    case "large":
      return 1;
    case "tablet":
      return 2;
    case "desktop":
      return 2;
  }
}

export function getCardWidth(padding = 16): number {
  const cols = getCardColumns();
  const usableWidth = Math.min(SCREEN_WIDTH, MAX_CONTENT_WIDTH);
  const totalPadding = padding * 2 + (cols - 1) * padding;
  return (usableWidth - totalPadding) / cols;
}

/** Centered container style with max width and horizontal padding. */
export function centeredContainer(paddingH = 24): ViewStyle {
  return {
    width: "100%",
    maxWidth: MAX_CONTENT_WIDTH,
    alignSelf: "center" as const,
    paddingHorizontal: paddingH,
  };
}

/** Screen scroll content style — centered with bottom padding. */
export function scrollContent(paddingH = 24): ViewStyle {
  return {
    ...centeredContainer(paddingH),
    paddingBottom: 48,
  };
}

/** Full-width container for landing/hero sections on web. */
export function fullWidthContent(): ViewStyle {
  return {
    width: "100%",
    maxWidth: 1200,
    alignSelf: "center" as const,
    paddingHorizontal: isWeb ? 48 : 24,
  };
}

export { SCREEN_WIDTH, SCREEN_HEIGHT, MAX_CONTENT_WIDTH };
