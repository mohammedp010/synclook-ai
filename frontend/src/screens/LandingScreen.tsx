import React, { useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
} from "react-native-reanimated";
import { useNavigation } from "@react-navigation/native";

import { GlowBackground } from "../components/ui/GlowBackground";
import { AnimatedEntry } from "../components/ui/AnimatedEntry";
import { LogoSvg } from "../components/svg/LogoSvg";
import { SparkleIcon } from "../components/svg/SparkleIcon";
import { WardrobeIllustration } from "../components/svg/WardrobeIllustration";
import { colors, typography, spacing, radius, shadow, glass } from "../theme/tokens";
import { wp, hp, isWeb, fullWidthContent } from "../utils/responsive";
import { pressIn, pressOut, floatLoop, pulseLoop } from "../utils/animations";

/* ── Feature data ─────────────────────────────────────────── */
const FEATURES = [
  {
    icon: "👁️",
    title: "AI Vision",
    desc: "Upload a photo and our AI instantly detects clothing type, color, pattern, and style.",
  },
  {
    icon: "🎨",
    title: "Smart Styling",
    desc: "Color theory, pattern matching, and occasion-aware rules create perfectly coordinated outfits.",
  },
  {
    icon: "✨",
    title: "Outfit Suggestions",
    desc: "Get complete, curated looks with multiple items that complement your wardrobe.",
  },
  {
    icon: "🛍️",
    title: "Shop the Look",
    desc: "Each recommendation links to real products you can buy — from top retailers.",
  },
];

const STEPS = [
  { num: "1", label: "Upload a photo of your clothing" },
  { num: "2", label: "AI analyzes color, style & pattern" },
  { num: "3", label: "Get curated outfit recommendations" },
];

/* ── Component ────────────────────────────────────────────── */
export default function LandingScreen() {
  const navigation = useNavigation<any>();

  // Floating animation for hero illustration
  const floatY = useSharedValue(0);
  useEffect(() => {
    floatY.value = floatLoop(8, 4000);
  }, []);
  const floatStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: floatY.value }],
  }));

  // Glow pulse for CTA
  const glowOpacity = useSharedValue(0.15);
  useEffect(() => {
    glowOpacity.value = pulseLoop(0.1, 0.3, 2000);
  }, []);
  const glowStyle = useAnimatedStyle(() => ({
    opacity: glowOpacity.value,
  }));

  // CTA press
  const ctaScale = useSharedValue(1);
  const ctaAnim = useAnimatedStyle(() => ({
    transform: [{ scale: ctaScale.value }],
  }));

  return (
    <GlowBackground>
      <SafeAreaView style={styles.safe}>
        <ScrollView
          contentContainerStyle={styles.scroll}
          showsVerticalScrollIndicator={false}
        >
          {/* ─── Nav bar ─── */}
          <AnimatedEntry index={0}>
            <View style={styles.nav}>
              <View style={styles.navLeft}>
                <LogoSvg size={36} animated={false} />
                <Text style={styles.navBrand}>Synclook</Text>
              </View>
              <View style={styles.navBadge}>
                <SparkleIcon size={10} color={colors.brand[300]} />
                <Text style={styles.navBadgeText}>AI-Powered</Text>
              </View>
            </View>
          </AnimatedEntry>

          {/* ─── Hero ─── */}
          <AnimatedEntry index={1}>
            <View style={styles.hero}>
              <Text style={styles.heroLabel}>AI FASHION AGENT</Text>
              <Text style={styles.heroTitle}>
                Your personal{"\n"}AI stylist
              </Text>
              <Text style={styles.heroDesc}>
                Upload any clothing item and get instant, AI-curated outfit
                recommendations powered by computer vision and style intelligence.
              </Text>
            </View>
          </AnimatedEntry>

          {/* ─── Hero illustration ─── */}
          <AnimatedEntry index={2}>
            <Animated.View style={[styles.heroIllustration, floatStyle]}>
              <WardrobeIllustration
                width={isWeb ? 340 : wp(75)}
                height={isWeb ? 200 : hp(22)}
              />
            </Animated.View>
          </AnimatedEntry>

          {/* ─── How it works ─── */}
          <AnimatedEntry index={3}>
            <View style={styles.stepsSection}>
              <Text style={styles.sectionLabel}>HOW IT WORKS</Text>
              <View style={styles.stepsRow}>
                {STEPS.map((step, i) => (
                  <View key={i} style={styles.stepCard}>
                    <View style={styles.stepNum}>
                      <Text style={styles.stepNumText}>{step.num}</Text>
                    </View>
                    <Text style={styles.stepLabel}>{step.label}</Text>
                  </View>
                ))}
              </View>
            </View>
          </AnimatedEntry>

          {/* ─── Feature cards ─── */}
          <AnimatedEntry index={4}>
            <View style={styles.featuresSection}>
              <Text style={styles.sectionLabel}>WHAT YOU GET</Text>
              <View style={styles.featuresGrid}>
                {FEATURES.map((f, i) => (
                  <View key={i} style={styles.featureCard}>
                    <Text style={styles.featureIcon}>{f.icon}</Text>
                    <Text style={styles.featureTitle}>{f.title}</Text>
                    <Text style={styles.featureDesc}>{f.desc}</Text>
                  </View>
                ))}
              </View>
            </View>
          </AnimatedEntry>

          {/* ─── Tech strip ─── */}
          {/* <AnimatedEntry index={5}>
            <View style={styles.techStrip}>
              {["CLIP", "BLIP-2", "GPT-4o", "Real-time SSE"].map((t) => (
                <View key={t} style={styles.techPill}>
                  <Text style={styles.techPillText}>{t}</Text>
                </View>
              ))}
            </View>
          </AnimatedEntry> */}

          {/* ─── CTA ─── */}
          <AnimatedEntry index={6}>
            <View style={styles.ctaSection}>
              <Animated.View style={[styles.ctaGlow, glowStyle]} />
              <TouchableOpacity
                activeOpacity={1}
                onPressIn={() => { ctaScale.value = pressIn(); }}
                onPressOut={() => { ctaScale.value = pressOut(); }}
                onPress={() => navigation.navigate("Home")}
              >
                <Animated.View style={[styles.ctaButton, ctaAnim]}>
                  <Text style={styles.ctaText}>Let's Start</Text>
                  <Text style={styles.ctaArrow}>→</Text>
                </Animated.View>
              </TouchableOpacity>
              <Text style={styles.ctaHint}>Free • No sign-up required</Text>
            </View>
          </AnimatedEntry>

          {/* ─── Footer ─── */}
          <View style={styles.footer}>
            <Text style={styles.footerText}>
              Powered by multi-agent AI pipeline
            </Text>
          </View>
        </ScrollView>
      </SafeAreaView>
    </GlowBackground>
  );
}

/* ── Styles ────────────────────────────────────────────────── */
const styles = StyleSheet.create({
  safe: { flex: 1 },
  scroll: {
    ...fullWidthContent(),
    paddingBottom: 64,
  },

  /* Nav */
  nav: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: spacing.lg,
    paddingBottom: spacing.xl,
  },
  navLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  navBrand: {
    ...typography.heading.sm,
    color: colors.text.primary,
  },
  navBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    backgroundColor: "rgba(139,92,246,0.12)",
    borderRadius: radius.full,
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderWidth: 1,
    borderColor: "rgba(139,92,246,0.2)",
  },
  navBadgeText: {
    ...typography.label.sm,
    color: colors.brand[300],
    fontSize: 11,
  },

  /* Hero */
  hero: {
    alignItems: "center",
    paddingTop: isWeb ? 48 : spacing.lg,
    paddingBottom: spacing.xl,
  },
  heroLabel: {
    ...typography.label.sm,
    color: colors.brand[400],
    textTransform: "uppercase",
    letterSpacing: 2,
    marginBottom: spacing.md,
  },
  heroTitle: {
    fontFamily: "SpaceGrotesk_700Bold",
    fontSize: isWeb ? 52 : 36,
    lineHeight: isWeb ? 60 : 44,
    color: colors.text.primary,
    textAlign: "center",
    marginBottom: spacing.md,
  },
  heroDesc: {
    ...typography.body.lg,
    color: colors.text.secondary,
    textAlign: "center",
    maxWidth: 520,
    lineHeight: 26,
  },

  /* Hero illustration */
  heroIllustration: {
    alignItems: "center",
    marginBottom: isWeb ? 56 : spacing.xl,
  },

  /* Section label */
  sectionLabel: {
    ...typography.label.sm,
    color: colors.text.tertiary,
    textTransform: "uppercase",
    letterSpacing: 2,
    textAlign: "center",
    marginBottom: spacing.lg,
  },

  /* Steps */
  stepsSection: {
    marginBottom: isWeb ? 64 : spacing.xl,
  },
  stepsRow: {
    flexDirection: isWeb ? "row" : "column",
    gap: spacing.md,
    ...(isWeb ? { justifyContent: "center" as const } : {}),
  },
  stepCard: {
    ...glass.card,
    borderRadius: radius.xl,
    padding: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    ...(isWeb ? { flex: 1, maxWidth: 340 } : {}),
  },
  stepNum: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.brand[600],
    alignItems: "center",
    justifyContent: "center",
  },
  stepNumText: {
    ...typography.label.lg,
    color: colors.text.onBrand,
  },
  stepLabel: {
    ...typography.body.md,
    color: colors.text.primary,
    flex: 1,
  },

  /* Features */
  featuresSection: {
    marginBottom: isWeb ? 64 : spacing.xl,
  },
  featuresGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
    ...(isWeb
      ? { justifyContent: "center" as const }
      : {}),
  },
  featureCard: {
    ...glass.elevated,
    borderRadius: radius.xl,
    padding: spacing.lg,
    ...(isWeb
      ? { width: "48%" as any, maxWidth: 440 }
      : { width: "100%" as any }),
    gap: spacing.sm,
  },
  featureIcon: {
    fontSize: 28,
    marginBottom: 4,
  },
  featureTitle: {
    ...typography.label.lg,
    color: colors.text.primary,
  },
  featureDesc: {
    ...typography.body.sm,
    color: colors.text.secondary,
    lineHeight: 20,
  },

  /* Tech strip */
  techStrip: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "center",
    gap: spacing.sm,
    marginBottom: isWeb ? 64 : spacing.xl,
  },
  techPill: {
    backgroundColor: colors.brand[900],
    borderRadius: radius.full,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: colors.brand[700],
  },
  techPillText: {
    ...typography.label.sm,
    color: colors.brand[300],
  },

  /* CTA */
  ctaSection: {
    alignItems: "center",
    paddingVertical: isWeb ? 48 : spacing.xl,
    position: "relative",
  },
  ctaGlow: {
    position: "absolute",
    width: 300,
    height: 300,
    borderRadius: 150,
    backgroundColor: colors.brand[600],
    top: -60,
  },
  ctaButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.brand[600],
    borderRadius: radius.xl,
    paddingVertical: isWeb ? 18 : spacing.md + 2,
    paddingHorizontal: isWeb ? 56 : spacing.xl + 16,
    gap: spacing.sm,
    ...shadow.lg,
  },
  ctaText: {
    fontFamily: "SpaceGrotesk_700Bold",
    fontSize: isWeb ? 20 : 17,
    color: colors.text.onBrand,
  },
  ctaArrow: {
    fontSize: isWeb ? 22 : 18,
    color: colors.text.onBrand,
  },
  ctaHint: {
    ...typography.body.xs,
    color: colors.text.tertiary,
    marginTop: spacing.md,
  },

  /* Footer */
  footer: {
    alignItems: "center",
    paddingTop: spacing.xl,
    paddingBottom: spacing.md,
  },
  footerText: {
    ...typography.body.xs,
    color: colors.text.tertiary,
  },
});
