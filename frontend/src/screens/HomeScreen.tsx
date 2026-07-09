import React, { useCallback, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
} from "react-native-reanimated";
import * as ImagePicker from "expo-image-picker";
import * as Haptics from "expo-haptics";
import { useNavigation } from "@react-navigation/native";

import { LogoSvg } from "../components/svg/LogoSvg";
import { WardrobeIllustration } from "../components/svg/WardrobeIllustration";
import { SparkleIcon } from "../components/svg/SparkleIcon";
import { AnimatedEntry } from "../components/ui/AnimatedEntry";
import { GlowBackground } from "../components/ui/GlowBackground";
import { useAppStore } from "../store/useAppStore";
import { colors, typography, spacing, radius, shadow, glass } from "../theme/tokens";
import { scale, wp, hp, fullWidthContent, isWideWeb } from "../utils/responsive";
import { pressIn, pressOut, floatLoop } from "../utils/animations";
import type { ShoppingIntent } from "../types/api";

const SHOPPING_INTENT_OPTIONS: { label: string; value: ShoppingIntent }[] = [
  { label: "Menswear", value: "menswear" },
  { label: "Womenswear", value: "womenswear" },
  { label: "Unisex", value: "unisex" },
  { label: "All", value: "all" },
];

const IS_WIDE_LAYOUT = isWideWeb;

function toDisplayLabel(value: string): string {
  return value.replace(/[_-]/g, " ");
}

export default function HomeScreen() {
  const navigation = useNavigation<any>();
  const setCurrentImage = useAppStore((s) => s.setCurrentImage);
  const analysisHistory = useAppStore((s) => s.analysisHistory);
  const shoppingIntent = useAppStore((s) => s.shoppingIntent);
  const setShoppingIntent = useAppStore((s) => s.setShoppingIntent);
  const includeProducts = useAppStore((s) => s.includeProducts);
  const setIncludeProducts = useAppStore((s) => s.setIncludeProducts);
  const userIntent = useAppStore((s) => s.userIntent);
  const setUserIntent = useAppStore((s) => s.setUserIntent);

  // Floating animation for illustration
  const floatY = useSharedValue(0);
  useEffect(() => {
    floatY.value = floatLoop(6, 3500);
  }, []);
  const floatStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: floatY.value }],
  }));

  // CTA press animation
  const ctaScale = useSharedValue(1);
  const ctaAnimStyle = useAnimatedStyle(() => ({
    transform: [{ scale: ctaScale.value }],
  }));

  const pickFromGallery = useCallback(async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) return;

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
      allowsEditing: true,
      aspect: [3, 4],
    });

    if (!result.canceled && result.assets[0]) {
      const uri = result.assets[0].uri;
      setCurrentImage(uri);
      navigation.navigate("Analysis", { imageUri: uri });
    }
  }, [navigation, setCurrentImage]);

  const openCamera = useCallback(async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);

    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) return;

    const result = await ImagePicker.launchCameraAsync({
      quality: 0.85,
      allowsEditing: true,
      aspect: [3, 4],
    });

    if (!result.canceled && result.assets[0]) {
      const uri = result.assets[0].uri;
      setCurrentImage(uri);
      navigation.navigate("Analysis", { imageUri: uri });
    }
  }, [navigation, setCurrentImage]);

  return (
    <GlowBackground>
      <SafeAreaView style={styles.container}>
        <ScrollView
          contentContainerStyle={styles.scroll}
          showsVerticalScrollIndicator={false}
        >
          {/* Logo + badge */}
          <AnimatedEntry index={0}>
            <View style={styles.logoRow}>
              <LogoSvg size={44} animated />
              <View style={styles.aiBadge}>
                <SparkleIcon size={10} color="#c4b5fd" animated />
                <Text style={styles.aiBadgeText}>AI Stylist</Text>
              </View>
            </View>
          </AnimatedEntry>

          {/* ── Two-column hero layout (side-by-side on web, stacked on mobile) ── */}
          <View style={styles.heroLayout}>

            {/* LEFT — text, CTAs, settings */}
            <View style={styles.leftCol}>
              <AnimatedEntry index={1}>
                <View style={styles.heroSection}>
                  <Text style={styles.heroTitle}>
                    Find your{"\n"}perfect outfit
                  </Text>
                  <Text style={styles.heroSub}>
                    Upload any clothing item and get{"\n"}AI-curated outfit recommendations instantly.
                  </Text>
                </View>
              </AnimatedEntry>

              <AnimatedEntry index={3}>
                <View style={styles.ctaGroup}>
                  <TouchableOpacity
                    activeOpacity={1}
                    onPressIn={() => { ctaScale.value = pressIn(); }}
                    onPressOut={() => { ctaScale.value = pressOut(); }}
                    onPress={pickFromGallery}
                    style={styles.ctaTouchable}
                  >
                    <Animated.View style={[styles.ctaButton, ctaAnimStyle]}>
                      <Text style={styles.ctaIcon}>✨</Text>
                      <Text style={styles.ctaText}>Upload & Style</Text>
                    </Animated.View>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={styles.secondaryBtn}
                    onPress={openCamera}
                    activeOpacity={0.7}
                  >
                    <Text style={styles.secondaryBtnText}>📷  Take a Photo</Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={styles.secondaryBtn}
                    onPress={() => {
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                      navigation.navigate("Wardrobe");
                    }}
                    activeOpacity={0.7}
                  >
                    <Text style={styles.secondaryBtnText}>👔  My Wardrobe</Text>
                  </TouchableOpacity>
                </View>
              </AnimatedEntry>

              <AnimatedEntry index={4}>
                <View style={styles.settingsCard}>
                  <Text style={styles.settingsLabel}>Styling request (optional)</Text>
                  <TextInput
                    style={styles.intentInput}
                    value={userIntent}
                    onChangeText={setUserIntent}
                    placeholder='e.g. "rainy dinner under ₹5,000" or "office-safe streetwear"'
                    placeholderTextColor={colors.text.tertiary}
                    multiline={false}
                    returnKeyType="done"
                  />

                  <Text style={styles.settingsLabel}>Shopping intent</Text>
                  <View style={styles.pillRow}>
                    {SHOPPING_INTENT_OPTIONS.map((opt) => {
                      const active = shoppingIntent === opt.value;
                      return (
                        <TouchableOpacity
                          key={opt.value}
                          style={[styles.pill, active && styles.pillActive]}
                          onPress={() => {
                            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                            setShoppingIntent(opt.value);
                          }}
                          activeOpacity={0.75}
                        >
                          <Text
                            style={[styles.pillText, active && styles.pillTextActive]}
                            numberOfLines={1}
                            adjustsFontSizeToFit
                            minimumFontScale={0.82}
                          >
                            {opt.label}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>

                  <View style={styles.toggleRow}>
                    <Text style={styles.toggleLabel}>Product links</Text>
                    <View style={styles.togglePills}>
                      <TouchableOpacity
                        style={[styles.togglePill, includeProducts && styles.togglePillActive]}
                        onPress={() => setIncludeProducts(true)}
                        activeOpacity={0.75}
                      >
                        <Text style={[styles.toggleText, includeProducts && styles.toggleTextActive]}>On</Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={[styles.togglePill, !includeProducts && styles.togglePillActive]}
                        onPress={() => setIncludeProducts(false)}
                        activeOpacity={0.75}
                      >
                        <Text style={[styles.toggleText, !includeProducts && styles.toggleTextActive]}>Off</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                </View>
              </AnimatedEntry>
            </View>

            {/* RIGHT — floating illustration */}
            <AnimatedEntry index={2}>
              <Animated.View style={[styles.illustrationWrap, floatStyle]}>
                <WardrobeIllustration
                  width={IS_WIDE_LAYOUT ? 480 : wp(70)}
                  height={IS_WIDE_LAYOUT ? 300 : hp(22)}
                />
              </Animated.View>
            </AnimatedEntry>

          </View>

          {/* Recent analyses */}
          {analysisHistory.length > 0 && (
            <AnimatedEntry index={5}>
              <View style={styles.historySection}>
                <Text style={styles.historyTitle}>Recent</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  {analysisHistory.slice(0, 5).map((item) => {
                    const attrs = item.detected_attributes;
                    return (
                      <TouchableOpacity
                        key={item.request_id}
                        style={styles.historyCard}
                        onPress={() => {
                          Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                          navigation.navigate("Results");
                        }}
                        activeOpacity={0.75}
                      >
                        <Text style={styles.historyType}>
                          {attrs ? toDisplayLabel(attrs.clothing_type) : "partial"}
                        </Text>
                        <Text style={styles.historyColor}>
                          {attrs ? attrs.primary_color : "—"}
                        </Text>
                        <Text style={styles.historyRecs}>
                          {item.recommendations.length} looks
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </ScrollView>
              </View>
            </AnimatedEntry>
          )}
        </ScrollView>
      </SafeAreaView>
    </GlowBackground>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scroll: {
    ...fullWidthContent(),
    paddingHorizontal: IS_WIDE_LAYOUT ? 80 : 24,
    alignItems: "center",
    paddingBottom: 64,
  },

  // Logo row
  logoRow: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: IS_WIDE_LAYOUT ? "flex-start" : "center",
    gap: spacing.sm,
    paddingTop: IS_WIDE_LAYOUT ? spacing.xl : spacing.lg,
    marginBottom: IS_WIDE_LAYOUT ? 48 : spacing.xl,
    width: "100%",
  },
  aiBadge: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "rgba(139, 92, 246, 0.15)",
    borderRadius: radius.full,
    paddingHorizontal: 10,
    paddingVertical: 4,
    gap: 4,
    borderWidth: 1,
    borderColor: "rgba(139, 92, 246, 0.25)",
  },
  aiBadgeText: {
    ...typography.label.sm,
    color: colors.brand[300],
    fontSize: IS_WIDE_LAYOUT ? 12 : 10,
  },

  // Hero
  heroSection: {
    alignItems: IS_WIDE_LAYOUT ? "flex-start" : "center",
    marginBottom: IS_WIDE_LAYOUT ? 28 : spacing.lg,
  },
  heroTitle: {
    fontFamily: "SpaceGrotesk_700Bold",
    fontSize: IS_WIDE_LAYOUT ? 52 : 32,
    lineHeight: IS_WIDE_LAYOUT ? 62 : 40,
    color: colors.text.primary,
    textAlign: IS_WIDE_LAYOUT ? "left" : "center",
    marginBottom: spacing.sm,
  },
  heroSub: {
    ...typography.body.md,
    fontSize: IS_WIDE_LAYOUT ? 17 : undefined,
    lineHeight: IS_WIDE_LAYOUT ? 26 : undefined,
    color: colors.text.secondary,
    textAlign: IS_WIDE_LAYOUT ? "left" : "center",
    maxWidth: IS_WIDE_LAYOUT ? 420 : undefined,
  },

  // Two-column hero layout
  heroLayout: {
    flexDirection: IS_WIDE_LAYOUT ? "row" : "column",
    alignItems: IS_WIDE_LAYOUT ? "center" : "stretch",
    width: "100%",
    gap: IS_WIDE_LAYOUT ? 80 : 0,
    paddingVertical: IS_WIDE_LAYOUT ? 40 : 0,
  },
  leftCol: {
    flex: IS_WIDE_LAYOUT ? 1 : undefined,
    width: IS_WIDE_LAYOUT ? undefined : "100%",
    alignItems: IS_WIDE_LAYOUT ? "flex-start" : "center",
    minWidth: IS_WIDE_LAYOUT ? 0 : undefined,
  },
  ctaGroup: {
    width: "100%",
    marginBottom: IS_WIDE_LAYOUT ? 0 : 0,
  },
  ctaTouchable: {
    width: "100%",
  },

  // Illustration — right column on web
  illustrationWrap: {
    flex: IS_WIDE_LAYOUT ? 1 : undefined,
    alignItems: "center",
    justifyContent: IS_WIDE_LAYOUT ? "center" : undefined,
    marginBottom: IS_WIDE_LAYOUT ? 0 : spacing.xl,
    opacity: 0.9,
    minWidth: IS_WIDE_LAYOUT ? 0 : undefined,
  },

  // CTA
  ctaButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.brand[600],
    borderRadius: radius.xl,
    paddingVertical: IS_WIDE_LAYOUT ? 18 : spacing.md + 2,
    paddingHorizontal: IS_WIDE_LAYOUT ? 40 : spacing.xl,
    gap: spacing.sm,
    width: "100%",
    ...shadow.lg,
  },
  ctaIcon: {
    fontSize: IS_WIDE_LAYOUT ? 22 : 20,
  },
  ctaText: {
    ...typography.label.lg,
    fontSize: IS_WIDE_LAYOUT ? 18 : undefined,
    color: colors.text.onBrand,
  },
  secondaryBtn: {
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.xl,
    paddingVertical: IS_WIDE_LAYOUT ? 16 : spacing.md,
    marginTop: spacing.sm,
    width: "100%",
    borderWidth: 1,
    borderColor: colors.surface.border,
    backgroundColor: "rgba(26, 26, 46, 0.5)",
  },
  secondaryBtnText: {
    ...typography.label.md,
    fontSize: IS_WIDE_LAYOUT ? 16 : undefined,
    color: colors.text.secondary,
  },

  // Settings card
  settingsCard: {
    ...glass.card,
    borderRadius: radius.xl,
    padding: IS_WIDE_LAYOUT ? 24 : spacing.md,
    marginTop: IS_WIDE_LAYOUT ? 24 : spacing.xl,
    width: "100%",
    gap: IS_WIDE_LAYOUT ? 18 : spacing.md,
  },
  intentInput: {
    ...typography.body.sm,
    color: colors.text.primary,
    backgroundColor: colors.surface.tertiary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.surface.border,
    paddingHorizontal: spacing.md,
    paddingVertical: IS_WIDE_LAYOUT ? 12 : spacing.sm + 2,
  },
  settingsLabel: {
    ...typography.label.sm,
    color: colors.text.tertiary,
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  pillRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  pill: {
    flexGrow: 1,
    flexBasis: IS_WIDE_LAYOUT ? 0 : "47%",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: IS_WIDE_LAYOUT ? 12 : spacing.sm,
    paddingHorizontal: IS_WIDE_LAYOUT ? 16 : spacing.md,
    borderRadius: radius.lg,
    gap: 4,
    backgroundColor: colors.surface.tertiary,
    borderWidth: 1,
    borderColor: "transparent",
  },
  pillActive: {
    backgroundColor: "rgba(139, 92, 246, 0.18)",
    borderColor: colors.brand[500],
  },
  pillText: {
    ...typography.label.sm,
    fontSize: IS_WIDE_LAYOUT ? 14 : 12,
    color: colors.text.tertiary,
    textAlign: "center",
  },
  pillTextActive: {
    color: colors.brand[300],
  },
  toggleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  toggleLabel: {
    ...typography.body.sm,
    color: colors.text.tertiary,
  },
  togglePills: {
    flexDirection: "row",
    gap: spacing.xs,
  },
  togglePill: {
    paddingHorizontal: IS_WIDE_LAYOUT ? 20 : spacing.md,
    paddingVertical: IS_WIDE_LAYOUT ? 8 : 6,
    borderRadius: radius.full,
    backgroundColor: colors.surface.tertiary,
    borderWidth: 1,
    borderColor: "transparent",
  },
  togglePillActive: {
    backgroundColor: "rgba(139, 92, 246, 0.18)",
    borderColor: colors.brand[500],
  },
  toggleText: {
    ...typography.label.sm,
    color: colors.text.tertiary,
  },
  toggleTextActive: {
    color: colors.brand[300],
  },

  // History
  historySection: {
    width: "100%",
    marginTop: IS_WIDE_LAYOUT ? 48 : spacing.xl,
  },
  historyTitle: {
    ...typography.label.sm,
    color: colors.text.tertiary,
    textTransform: "uppercase",
    letterSpacing: 1,
    marginBottom: spacing.sm,
  },
  historyCard: {
    ...glass.card,
    borderRadius: radius.lg,
    padding: IS_WIDE_LAYOUT ? 16 : spacing.md,
    marginRight: spacing.sm,
    width: IS_WIDE_LAYOUT ? 150 : scale(110),
  },
  historyType: {
    ...typography.label.sm,
    color: colors.text.primary,
    textTransform: "capitalize",
  },
  historyColor: {
    ...typography.body.xs,
    color: colors.text.secondary,
    marginTop: 2,
    textTransform: "capitalize",
  },
  historyRecs: {
    ...typography.body.xs,
    color: colors.brand[400],
    marginTop: spacing.xs,
  },
});
