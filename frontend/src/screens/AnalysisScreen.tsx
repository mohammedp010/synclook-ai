import React, { useEffect, memo } from "react";
import {
  View,
  Text,
  StyleSheet,
  Image,
  TouchableOpacity,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  withSequence,
  Easing,
} from "react-native-reanimated";
import { useNavigation, useRoute } from "@react-navigation/native";
import Svg, { Path, Circle } from "react-native-svg";

import { useAnalysis, type StageState } from "../hooks/useAnalysis";
import { ProgressRing } from "../components/ui/ProgressRing";
import { AnalyzingWave } from "../components/svg/AnalyzingWave";
import { AnimatedEntry } from "../components/ui/AnimatedEntry";
import { GlowBackground } from "../components/ui/GlowBackground";
import { colors, typography, spacing, radius, shadow, glass } from "../theme/tokens";
import { wp, scale, scrollContent, isWeb } from "../utils/responsive";

const STAGE_MAP: Record<string, { label: string }> = {
  start:          { label: "Starting analysis" },
  intent:         { label: "Understanding your request" },
  vision:         { label: "Analyzing clothing" },
  styling:        { label: "Matching style rules" },
  recommendation: { label: "Crafting outfit suggestions" },
  wardrobe:       { label: "Checking your wardrobe" },
  shopping:       { label: "Finding products" },
  verifier:       { label: "Quality-checking looks" },
};

export default function AnalysisScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute<any>();
  const imageUri: string = route.params?.imageUri ?? "";

  const { status, stages, result, error, warnings, elapsed, analyze, reset } = useAnalysis();

  const pulseScale = useSharedValue(1);
  const pulseOpacity = useSharedValue(0.6);

  useEffect(() => {
    pulseScale.value = withRepeat(
      withTiming(1.15, { duration: 1200, easing: Easing.inOut(Easing.sin) }),
      -1,
      true
    );
    pulseOpacity.value = withRepeat(
      withSequence(
        withTiming(1, { duration: 900 }),
        withTiming(0.5, { duration: 900 })
      ),
      -1,
      true
    );
  }, []);

  const pulseStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pulseScale.value }],
    opacity: pulseOpacity.value,
  }));

  // Start analysis on mount
  useEffect(() => {
    if (imageUri) {
      analyze(imageUri);
    }
  }, [imageUri]);

  // Navigate to results when done
  useEffect(() => {
    if (status === "done" && result) {
      const timer = setTimeout(() => {
        navigation.replace("Results");
      }, 600);
      return () => clearTimeout(timer);
    }
  }, [status, result, navigation]);

  // Progress over the stages the planner actually routes through: pending
  // stages are dropped from the list when the stream finishes, and until
  // then the denominator is simply the full displayed list.
  const doneCount = stages.filter((s) => s.status === "done").length;
  const progress = stages.length > 0 ? doneCount / stages.length : 0;

  return (
    <GlowBackground>
      <SafeAreaView style={styles.container}>
        <View style={styles.content}>
          {/* Image preview */}
          {imageUri ? (
            <AnimatedEntry index={0}>
              <View style={styles.imageContainer}>
                <Image
                  source={{ uri: imageUri }}
                  style={styles.image}
                  resizeMode="cover"
                />
                <View style={styles.imageOverlay} />
              </View>
            </AnimatedEntry>
          ) : null}

          {/* Progress ring */}
          <AnimatedEntry index={1}>
            <View style={styles.ringContainer}>
              <Animated.View style={[styles.glowRing, pulseStyle]} />
              <ProgressRing size={scale(130)} strokeWidth={6} progress={progress}>
                <View style={styles.ringContent}>
                  <Text style={styles.progressPercent}>
                    {Math.round(progress * 100)}%
                  </Text>
                  <Text style={styles.progressLabel}>analyzing</Text>
                </View>
              </ProgressRing>
            </View>
          </AnimatedEntry>

          {/* Status label */}
          <AnimatedEntry index={2}>
            <Text style={styles.statusTitle}>
              {status === "error" ? "Analysis Failed" : "Analyzing..."}
            </Text>
            <Text style={styles.statusSub}>
              {status === "error"
                ? error ?? "Something went wrong"
                : "Our AI is working on your outfit"}
            </Text>
            {warnings.length > 0 && (
              <View style={styles.warningBanner}>
                <Text style={styles.warningTitle}>Partial result warning</Text>
                <Text style={styles.warningText} numberOfLines={2}>
                  {warnings[0]}
                </Text>
              </View>
            )}
          </AnimatedEntry>

          {/* Wave animation */}
          {status === "analyzing" && (
            <AnimatedEntry index={3}>
              <View style={styles.waveContainer}>
                <AnalyzingWave width={wp(85)} height={60} />
              </View>
            </AnimatedEntry>
          )}

          {/* Stage indicators */}
          <AnimatedEntry index={4}>
            <View style={styles.stagesContainer}>
              {stages.map((stage, i) => (
                <StageRow key={stage.stage} stage={stage} index={i} />
              ))}
            </View>
          </AnimatedEntry>

          {/* Elapsed time */}
          {status === "done" && elapsed > 0 && (
            <AnimatedEntry index={5}>
              <Text style={styles.elapsed}>
                Completed in {elapsed.toFixed(1)}s
              </Text>
            </AnimatedEntry>
          )}

          {/* Error retry */}
          {status === "error" && (
            <AnimatedEntry index={5}>
              <TouchableOpacity
                style={styles.retryBtn}
                onPress={() => {
                  reset();
                  if (imageUri) analyze(imageUri);
                }}
                activeOpacity={0.75}
              >
                <Text style={styles.retryText}>Retry Analysis</Text>
              </TouchableOpacity>
            </AnimatedEntry>
          )}
        </View>
      </SafeAreaView>
    </GlowBackground>
  );
}

function CheckIcon() {
  return (
    <Svg width={12} height={12} viewBox="0 0 12 12">
      <Path d="M2 6l3 3 5-5" stroke="#fff" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </Svg>
  );
}

function XIcon() {
  return (
    <Svg width={12} height={12} viewBox="0 0 12 12">
      <Path d="M3 3l6 6M9 3l-6 6" stroke="#fff" strokeWidth={1.8} strokeLinecap="round" fill="none" />
    </Svg>
  );
}

function ActiveDot() {
  return <Circle cx="6" cy="6" r="3" fill="#fff" />;
}

const StageRow = memo(function StageRow({ stage, index }: { stage: StageState; index: number }) {
  const info = STAGE_MAP[stage.stage] ?? { label: stage.stage };
  const isActive = stage.status === "active";
  const isDone = stage.status === "done";
  const isError = stage.status === "error";

  const dotColor = isDone
    ? colors.semantic.success
    : isError
    ? colors.semantic.error
    : isActive
    ? colors.brand[500]
    : colors.surface.border;

  return (
    <View style={styles.stageRow}>
      <View style={[styles.stageDot, { backgroundColor: dotColor }]}>
        {isDone ? (
          <CheckIcon />
        ) : isError ? (
          <XIcon />
        ) : isActive ? (
          <Svg width={12} height={12} viewBox="0 0 12 12"><ActiveDot /></Svg>
        ) : null}
      </View>
      <View style={styles.stageTextContainer}>
        <Text
          style={[
            styles.stageLabel,
            isActive && styles.stageLabelActive,
            isDone && styles.stageLabelDone,
          ]}
        >
          {info.label}
        </Text>
        {isActive && (
          <Text style={styles.stageMessage}>{stage.message}</Text>
        )}
      </View>
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    flex: 1,
    alignItems: "center",
    ...scrollContent(),
    paddingTop: spacing.lg,
  },
  imageContainer: {
    width: isWeb ? 120 : scale(90),
    height: isWeb ? 120 : scale(90),
    borderRadius: radius.xl,
    overflow: "hidden",
    marginBottom: spacing.xl,
    ...shadow.lg,
  },
  image: {
    width: "100%",
    height: "100%",
  },
  imageOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.2)",
  },
  ringContainer: {
    marginBottom: spacing.xl,
    alignItems: "center",
    justifyContent: "center",
  },
  glowRing: {
    position: "absolute",
    width: scale(150),
    height: scale(150),
    borderRadius: scale(75),
    backgroundColor: colors.brand[600],
    opacity: 0.15,
  },
  ringContent: {
    alignItems: "center",
    gap: 2,
  },
  progressPercent: {
    ...typography.heading.sm,
    color: colors.text.primary,
  },
  progressLabel: {
    ...typography.body.xs,
    color: colors.text.tertiary,
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  statusTitle: {
    ...typography.heading.sm,
    color: colors.text.primary,
    textAlign: "center",
    marginBottom: spacing.xs,
  },
  statusSub: {
    ...typography.body.md,
    color: colors.text.secondary,
    textAlign: "center",
    marginBottom: spacing.lg,
  },
  warningBanner: {
    alignSelf: "stretch",
    backgroundColor: colors.semantic.warningBg,
    borderColor: colors.semantic.warning + "44",
    borderWidth: 1,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginBottom: spacing.md,
  },
  warningTitle: {
    ...typography.label.sm,
    color: colors.semantic.warning,
    marginBottom: 2,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  warningText: {
    ...typography.body.xs,
    color: colors.text.secondary,
  },
  waveContainer: {
    marginBottom: spacing.lg,
  },
  stagesContainer: {
    width: "100%",
    gap: spacing.sm,
    marginBottom: spacing.xl,
  },
  stageRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    ...glass.card,
    borderRadius: radius.lg,
    padding: spacing.md,
    gap: spacing.md,
  },
  stageDot: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  stageTextContainer: {
    flex: 1,
  },
  stageLabel: {
    ...typography.body.md,
    color: colors.text.tertiary,
  },
  stageLabelActive: {
    color: colors.text.primary,
  },
  stageLabelDone: {
    color: colors.semantic.success,
  },
  stageMessage: {
    ...typography.body.xs,
    color: colors.text.secondary,
    marginTop: 2,
  },
  elapsed: {
    ...typography.body.sm,
    color: colors.text.tertiary,
    marginBottom: spacing.md,
  },
  retryBtn: {
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    backgroundColor: colors.brand[600],
    borderRadius: radius.xl,
    marginTop: spacing.md,
    minWidth: isWeb ? 200 : undefined,
    alignItems: "center" as any,
    ...shadow.md,
  },
  retryText: {
    ...typography.label.md,
    color: colors.text.onBrand,
  },
});
