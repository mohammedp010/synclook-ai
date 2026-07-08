import {
  withSpring,
  withTiming,
  withDelay,
  withSequence,
  withRepeat,
  Easing,
  type WithSpringConfig,
} from "react-native-reanimated";

// ── Spring presets ──────────────────────────────────────────

export const SPRING_SNAPPY: WithSpringConfig = {
  damping: 15,
  stiffness: 150,
  mass: 0.8,
};

export const SPRING_BOUNCY: WithSpringConfig = {
  damping: 8,
  stiffness: 120,
  mass: 1,
};

export const SPRING_GENTLE: WithSpringConfig = {
  damping: 20,
  stiffness: 90,
  mass: 1,
};

// ── Timing helpers ──────────────────────────────────────────

export const fadeIn = (delay = 0) =>
  withDelay(
    delay,
    withTiming(1, { duration: 400, easing: Easing.out(Easing.cubic) })
  );

export const staggeredEntry = (index: number) => ({
  opacity: withDelay(index * 80, withTiming(1, { duration: 350 })),
  translateY: withDelay(index * 80, withSpring(0, SPRING_SNAPPY)),
});

// ── Button press animation (scale 0.96 → 1) ────────────────

export const PRESS_SCALE = 0.96;

export const pressIn = () =>
  withSpring(PRESS_SCALE, { damping: 15, stiffness: 300 });

export const pressOut = () =>
  withSpring(1, SPRING_SNAPPY);

// ── Pulse animation for glow effects ────────────────────────

export const pulseLoop = (min = 0.6, max = 1, duration = 1500) =>
  withRepeat(
    withSequence(
      withTiming(max, { duration, easing: Easing.inOut(Easing.sin) }),
      withTiming(min, { duration, easing: Easing.inOut(Easing.sin) })
    ),
    -1,
    true
  );

// ── Floating animation for SVG illustrations ────────────────

export const floatLoop = (distance = 8, duration = 3000) =>
  withRepeat(
    withSequence(
      withTiming(-distance, { duration, easing: Easing.inOut(Easing.sin) }),
      withTiming(0, { duration, easing: Easing.inOut(Easing.sin) })
    ),
    -1,
    true
  );
