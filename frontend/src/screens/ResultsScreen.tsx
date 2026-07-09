import React, { useCallback, useState, memo } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Image,
  Linking,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
} from "react-native-reanimated";
import * as Haptics from "expo-haptics";
import { useNavigation } from "@react-navigation/native";

import { useAppStore } from "../store/useAppStore";
import { submitFeedback } from "../api/endpoints";
import { AnimatedEntry } from "../components/ui/AnimatedEntry";
import { Card } from "../components/ui/Card";
import { GlowBackground } from "../components/ui/GlowBackground";
import { SparkleIcon } from "../components/svg/SparkleIcon";
import Svg, { Path } from "react-native-svg";
import { HangerIcon } from "../components/svg/HangerIcon";
import {
  colors,
  typography,
  spacing,
  radius,
  shadow,
  glass,
  clothingColorMap,
} from "../theme/tokens";
import { wp, scale, scrollContent, isWeb } from "../utils/responsive";
import { pressIn, pressOut } from "../utils/animations";
import type { Recommendation, RecommendationItem, ProductLink } from "../types/api";

const SAFE_MODE_CONFIDENCE_THRESHOLD = 0.5;

function SparkleSmall({ color = colors.brand[400] }: { color?: string }) {
  return <SparkleIcon size={14} color={color} />
}

const ColorDot = memo(function ColorDot({ colorName }: { colorName: string }) {
  const hex = clothingColorMap[colorName] ?? colors.text.tertiary;
  const isLight = ["white", "cream", "yellow", "beige"].includes(colorName);
  return (
    <View
      style={[
        styles.colorDot,
        {
          backgroundColor: hex,
          borderColor: isLight ? colors.surface.tertiary : "transparent",
          borderWidth: isLight ? 1 : 0,
        },
      ]}
    />
  );
});

const ClothingChip = memo(function ClothingChip({ item }: { item: RecommendationItem }) {
  return (
    <View style={styles.chipRow}>
      <View style={styles.chip}>
        <ColorDot colorName={item.color} />
        <Text style={styles.chipText}>
          {item.color} {item.item_type.replace(/_/g, " ")}
        </Text>
      </View>
      {item.owned && (
        <View style={styles.ownedBadge}>
          <Text style={styles.ownedBadgeText}>👔 In your wardrobe</Text>
        </View>
      )}
    </View>
  );
});

const ProductCard = memo(function ProductCard({ product }: { product: ProductLink }) {
  const scaleVal = useSharedValue(1);
  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scaleVal.value }],
  }));

  const handleBuy = useCallback(async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const supported = await Linking.canOpenURL(product.link);
    if (supported) {
      await Linking.openURL(product.link);
    }
  }, [product.link]);

  return (
    <TouchableOpacity
      activeOpacity={1}
      onPressIn={() => { scaleVal.value = pressIn(); }}
      onPressOut={() => { scaleVal.value = pressOut(); }}
      onPress={handleBuy}
    >
      <Animated.View style={[styles.productCard, animStyle]}>
      {product.thumbnail ? (
        <Image
          source={{ uri: product.thumbnail }}
          style={styles.productThumb}
          resizeMode="cover"
        />
      ) : (
        <View style={[styles.productThumb, styles.productThumbFallback]}>
          <HangerIcon size={28} color={colors.brand[300]} />
        </View>
      )}
      <View style={styles.productInfo}>
        <Text style={styles.productTitle} numberOfLines={2}>
          {product.title}
        </Text>
        <View style={styles.productMeta}>
          <Text style={styles.productPrice}>{product.price}</Text>
          <View style={styles.productSourceBadge}>
            <Text style={styles.productSource}>{product.source}</Text>
          </View>
        </View>
        <View style={styles.buyButton}>
          <Text style={styles.buyButtonText}>View →</Text>
        </View>
      </View>
      </Animated.View>
    </TouchableOpacity>
  );
});

const OutfitCard = memo(function OutfitCard({
  recommendation,
  index,
  requestId,
}: {
  recommendation: Recommendation;
  index: number;
  requestId: string;
}) {
  const feedbackGiven = useAppStore((s) => s.feedbackGiven);
  const setFeedback = useAppStore((s) => s.setFeedback);
  const userId = useAppStore((s) => s.userId);
  const given = feedbackGiven[recommendation.id];
  const [showEvidence, setShowEvidence] = useState(false);
  const evidence = recommendation.evidence ?? [];

  const handleFeedback = useCallback(
    async (fb: "like" | "dislike") => {
      if (given) return;
      Haptics.impactAsync(
        fb === "like"
          ? Haptics.ImpactFeedbackStyle.Light
          : Haptics.ImpactFeedbackStyle.Medium
      );
      setFeedback(recommendation.id, fb);
      try {
        await submitFeedback({
          request_id: requestId,
          recommendation_id: recommendation.id,
          feedback: fb,
          user_id: userId ?? undefined,
        });
      } catch {
        // Non-fatal — feedback failure shouldn't break the UI
      }
    },
    [given, recommendation.id, requestId, userId, setFeedback]
  );

  return (
    <AnimatedEntry index={index} delay={100}>
      <View style={styles.card}>
        {/* Card header */}
        <View style={styles.cardHeader}>
          <View style={styles.cardHeaderLeft}>
            <HangerIcon size={18} />
            <Text style={styles.cardTitle}>Look {index + 1}</Text>
          </View>
          <View style={styles.confidenceBadge}>
            <Text style={styles.confidenceText}>
              {Math.round(recommendation.confidence * 100)}% match
            </Text>
          </View>
        </View>

        {/* Items */}
        <View style={styles.itemsList}>
          {recommendation.items.map((item, i) => (
            <View key={i} style={styles.itemRow}>
              <ClothingChip item={item} />
              <Text style={styles.itemReason}>{item.reason}</Text>
              {item.products && item.products.length > 0 && (
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  style={styles.productsScroll}
                  contentContainerStyle={styles.productsScrollContent}
                >
                  {item.products.map((product, pi) => (
                    <ProductCard key={pi} product={product} />
                  ))}
                </ScrollView>
              )}
            </View>
          ))}
        </View>

        {/* Style tags */}
        <View style={styles.tagsRow}>
          {recommendation.style_tags.map((tag, i) => (
            <View key={i} style={styles.tag}>
              <Text style={styles.tagText}>{tag.replace(/_/g, " ")}</Text>
            </View>
          ))}
        </View>

        {/* Overall explanation */}
        <View style={styles.explanationContainer}>
          <SparkleSmall color={colors.brand[400]} />
          <Text style={styles.explanation}>
            {recommendation.overall_explanation}
          </Text>
        </View>

        {/* Grounded evidence — the rule facts behind this look */}
        {evidence.length > 0 && (
          <View style={styles.evidenceSection}>
            <TouchableOpacity
              onPress={() => {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                setShowEvidence((v) => !v);
              }}
              activeOpacity={0.7}
            >
              <Text style={styles.evidenceToggle}>
                {showEvidence ? "▾ Why this look" : "▸ Why this look"}
              </Text>
            </TouchableOpacity>
            {showEvidence &&
              evidence.map((fact, i) => (
                <Text key={i} style={styles.evidenceFact}>
                  • {fact}
                </Text>
              ))}
          </View>
        )}

        {/* Feedback buttons */}
        <View style={styles.feedbackRow}>
          <Text style={styles.feedbackLabel}>How's this look?</Text>
          <View style={styles.feedbackButtons}>
            <TouchableOpacity
              style={[
                styles.feedbackBtn,
                given === "like" && styles.feedbackBtnLiked,
                given === "dislike" && styles.feedbackBtnDimmed,
              ]}
              onPress={() => handleFeedback("like")}
              activeOpacity={0.7}
              disabled={!!given}
            >
              <Text style={styles.feedbackBtnText}>Love it</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[
                styles.feedbackBtn,
                given === "dislike" && styles.feedbackBtnDisliked,
                given === "like" && styles.feedbackBtnDimmed,
              ]}
              onPress={() => handleFeedback("dislike")}
              activeOpacity={0.7}
              disabled={!!given}
            >
              <Text style={styles.feedbackBtnText}>Not for me</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </AnimatedEntry>
  );
});

export default function ResultsScreen() {
  const navigation = useNavigation<any>();
  const lastAnalysis = useAppStore((s) => s.lastAnalysis);
  const lastWarnings = useAppStore((s) => s.lastWarnings);
  const includeProducts = useAppStore((s) => s.includeProducts);

  if (!lastAnalysis) {
    return (
      <GlowBackground>
        <SafeAreaView style={styles.container}>
          <View style={styles.emptyState}>
            <HangerIcon size={48} color={colors.brand[400]} />
            <Text style={styles.emptyTitle}>No Analysis Yet</Text>
            <Text style={styles.emptySub}>Upload a clothing item to get started</Text>
            <TouchableOpacity
              style={styles.goHomeBtn}
              onPress={() => navigation.navigate("Home")}
              activeOpacity={0.75}
            >
              <Text style={styles.goHomeBtnText}>Go to Home</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </GlowBackground>
    );
  }

  const { detected_attributes: attrs, recommendations, request_id } = lastAnalysis;
  const showCaption = Boolean(attrs?.description && attrs?.description_relevant);

  if (!attrs) {
    return (
      <GlowBackground>
        <SafeAreaView style={styles.container}>
          <View style={styles.emptyState}>
            <Text style={styles.emptyTitle}>Analysis Incomplete</Text>
            <Text style={styles.emptySub}>Could not detect clothing attributes. Try a clearer image.</Text>
            <TouchableOpacity
              style={styles.goHomeBtn}
              onPress={() => navigation.navigate("Home")}
              activeOpacity={0.75}
            >
              <Text style={styles.goHomeBtnText}>Try Again</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </GlowBackground>
    );
  }

  const safeModeActive = attrs.confidence < SAFE_MODE_CONFIDENCE_THRESHOLD;

  return (
    <GlowBackground>
      <SafeAreaView style={styles.container}>
        <ScrollView
          contentContainerStyle={styles.scroll}
          showsVerticalScrollIndicator={false}
        >
          {/* Back + page title */}
          <AnimatedEntry index={0}>
            <View style={styles.pageHeader}>
              <TouchableOpacity
                onPress={() => navigation.navigate("Home")}
                style={styles.backBtn}
                activeOpacity={0.7}
              >
                <Text style={styles.backBtnText}>← New Analysis</Text>
              </TouchableOpacity>
              <Text style={styles.pageTitle}>Your Outfit Looks</Text>
              <Text style={styles.pageSub}>
                {recommendations.length} curated {recommendations.length === 1 ? "look" : "looks"} based on your item
              </Text>
            </View>
          </AnimatedEntry>

          {/* Warnings */}
          {lastWarnings.length > 0 && (
            <AnimatedEntry index={1}>
              <View style={styles.warningCard}>
                <Text style={styles.warningTitle}>Partial results</Text>
                <Text style={styles.warningBody}>{lastWarnings[0]}</Text>
              </View>
            </AnimatedEntry>
          )}

          {/* Detected attributes */}
          <AnimatedEntry index={2}>
            <View style={styles.attrCard}>
              <Text style={styles.attrTitle}>Detected</Text>
              <View style={styles.attrRow}>
                <View style={styles.attrChip}>
                  <ColorDot colorName={attrs.primary_color} />
                  <Text style={styles.attrChipText}>
                    {attrs.primary_color} {attrs.clothing_type.replace(/_/g, " ")}
                  </Text>
                </View>
                <View style={styles.attrChip}>
                  <Text style={styles.attrChipText}>
                    {attrs.pattern} · {attrs.style}
                  </Text>
                </View>
                <View style={styles.confChip}>
                  <Text style={styles.confChipText}>
                    {Math.round(attrs.confidence * 100)}%
                  </Text>
                </View>
              </View>
              {showCaption && (
                <Text style={styles.attrDesc}>{attrs.description}</Text>
              )}
              {safeModeActive && (
                <Text style={styles.safeModeText}>
                  Low confidence — conservative matching applied
                </Text>
              )}
            </View>
          </AnimatedEntry>

          {/* Outfit cards */}
          {recommendations.map((rec, i) => (
            <OutfitCard
              key={rec.id}
              recommendation={rec}
              index={i + 3}
              requestId={request_id}
            />
          ))}

          {recommendations.length === 0 && (
            <AnimatedEntry index={3}>
              <Text style={styles.noRecs}>
                No recommendations could be generated. Try a clearer image.
              </Text>
            </AnimatedEntry>
          )}

          {/* Try again CTA */}
          <AnimatedEntry index={recommendations.length + 4}>
            <TouchableOpacity
              style={styles.tryAgainBtn}
              onPress={() => {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                navigation.navigate("Home");
              }}
              activeOpacity={0.85}
            >
              <Text style={styles.tryAgainText}>Analyze Another Item</Text>
            </TouchableOpacity>
          </AnimatedEntry>
        </ScrollView>
      </SafeAreaView>
    </GlowBackground>
  );
}

const styles = StyleSheet.create({
  chipRow: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: spacing.xs,
  },
  ownedBadge: {
    backgroundColor: "rgba(74, 222, 128, 0.12)",
    borderColor: "rgba(74, 222, 128, 0.35)",
    borderWidth: 1,
    borderRadius: radius.full,
    paddingHorizontal: 10,
    paddingVertical: 3,
  },
  ownedBadgeText: {
    ...typography.label.sm,
    fontSize: 11,
    color: "#4ade80",
  },
  evidenceSection: {
    marginTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.surface.border,
    paddingTop: spacing.sm,
  },
  evidenceToggle: {
    ...typography.label.sm,
    color: colors.brand[300],
  },
  evidenceFact: {
    ...typography.body.xs,
    color: colors.text.tertiary,
    marginTop: 4,
    lineHeight: 16,
  },
  container: {
    flex: 1,
  },
  scroll: {
    ...scrollContent(),
    paddingBottom: spacing.xxl,
  },
  pageHeader: {
    paddingTop: spacing.md,
    marginBottom: spacing.lg,
    alignItems: "center",
  },
  backBtn: {
    alignSelf: "flex-start",
    marginBottom: spacing.sm,
  },
  backBtnText: {
    ...typography.label.sm,
    color: colors.brand[400],
  },
  pageTitle: {
    fontFamily: "SpaceGrotesk_700Bold",
    fontSize: isWeb ? 28 : 24,
    lineHeight: isWeb ? 34 : 30,
    color: colors.text.primary,
    textAlign: "center",
  },
  pageSub: {
    ...typography.body.sm,
    color: colors.text.tertiary,
    textAlign: "center",
    marginTop: 4,
  },
  /* Detected attributes */
  attrCard: {
    ...glass.card,
    borderRadius: radius.xl,
    padding: spacing.md,
    marginBottom: spacing.lg,
  },
  warningCard: {
    ...glass.card,
    borderRadius: radius.lg,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.semantic.warning + "44",
  },
  warningTitle: {
    ...typography.label.sm,
    color: colors.semantic.warning,
    textTransform: "uppercase",
    letterSpacing: 0.7,
    marginBottom: 4,
  },
  warningBody: {
    ...typography.body.sm,
    color: colors.text.secondary,
    lineHeight: 18,
  },
  attrTitle: {
    ...typography.label.sm,
    color: colors.text.tertiary,
    textTransform: "uppercase",
    letterSpacing: 0.8,
    marginBottom: spacing.sm,
    textAlign: "center",
  },
  attrRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "center",
    gap: spacing.xs,
    marginBottom: spacing.sm,
  },
  attrChip: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface.tertiary,
    borderRadius: radius.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    gap: 5,
  },
  attrChipText: {
    ...typography.body.xs,
    color: colors.text.primary,
    textTransform: "capitalize",
  },
  confChip: {
    backgroundColor: colors.brand[900],
    borderRadius: radius.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  confChipText: {
    ...typography.body.xs,
    color: colors.brand[300],
  },
  attrDesc: {
    ...typography.body.sm,
    color: colors.text.secondary,
    textAlign: "center",
    marginBottom: 4,
  },
  safeModeText: {
    ...typography.body.xs,
    color: colors.brand[300],
    textAlign: "center",
    marginTop: spacing.xs,
  },
  /* Outfit card */
  card: {
    ...glass.elevated,
    borderRadius: radius.xl,
    padding: spacing.lg,
    marginBottom: spacing.md,
  },
  cardHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: spacing.md,
  },
  cardHeaderLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
  },
  cardTitle: {
    ...typography.heading.sm,
    color: colors.text.primary,
    fontSize: 18,
  },
  confidenceBadge: {
    backgroundColor: colors.brand[900],
    borderRadius: radius.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
  },
  confidenceText: {
    ...typography.body.xs,
    color: colors.brand[300],
  },
  itemsList: {
    gap: spacing.md,
    marginBottom: spacing.md,
  },
  itemRow: {
    gap: 6,
  },
  productsScroll: {
    marginTop: spacing.xs,
  },
  productsScrollContent: {
    gap: spacing.sm,
    paddingVertical: 4,
  },
  productCard: {
    width: isWeb ? 180 : scale(140),
    ...glass.card,
    borderRadius: radius.lg,
    overflow: "hidden",
  },
  productThumb: {
    width: "100%",
    height: isWeb ? 130 : scale(100),
    backgroundColor: colors.surface.tertiary,
  },
  productThumbFallback: {
    alignItems: "center",
    justifyContent: "center",
  },
  productInfo: {
    padding: spacing.sm,
    gap: 4,
  },
  productTitle: {
    ...typography.body.xs,
    color: colors.text.primary,
    lineHeight: 14,
  },
  productMeta: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 4,
    flexWrap: "wrap",
  },
  productPrice: {
    ...typography.label.sm,
    color: colors.semantic.success,
  },
  productSourceBadge: {
    backgroundColor: colors.brand[900],
    borderRadius: radius.full,
    paddingHorizontal: 5,
    paddingVertical: 2,
  },
  productSource: {
    ...typography.body.xs,
    color: colors.brand[400],
    fontSize: 9,
  },
  buyButton: {
    marginTop: 4,
    backgroundColor: colors.brand[600],
    borderRadius: radius.md,
    paddingVertical: 5,
    alignItems: "center",
  },
  buyButtonText: {
    ...typography.label.sm,
    color: colors.text.onBrand,
    fontSize: 11,
  },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface.tertiary,
    borderRadius: radius.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
    alignSelf: "flex-start",
    gap: 5,
  },
  chipText: {
    ...typography.label.sm,
    color: colors.text.primary,
    textTransform: "capitalize",
  },
  itemReason: {
    ...typography.body.xs,
    color: colors.text.secondary,
    paddingLeft: spacing.xs,
    lineHeight: 16,
  },
  colorDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  tagsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "center",
    gap: spacing.xs,
    marginBottom: spacing.md,
  },
  tag: {
    backgroundColor: colors.brand[900],
    borderRadius: radius.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
  },
  tagText: {
    ...typography.body.xs,
    color: colors.brand[300],
    textTransform: "capitalize",
  },
  explanationContainer: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.xs,
    backgroundColor: colors.surface.tertiary,
    borderRadius: radius.lg,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  explanation: {
    flex: 1,
    ...typography.body.sm,
    color: colors.text.secondary,
    lineHeight: 20,
  },
  feedbackRow: {
    borderTopWidth: 1,
    borderTopColor: colors.surface.border,
    paddingTop: spacing.md,
    alignItems: "center",
  },
  feedbackLabel: {
    ...typography.body.xs,
    color: colors.text.tertiary,
    marginBottom: spacing.xs,
    textAlign: "center",
  },
  feedbackButtons: {
    flexDirection: "row",
    gap: spacing.sm,
  },
  feedbackBtn: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface.tertiary,
    borderRadius: radius.lg,
    paddingVertical: spacing.sm,
    gap: spacing.xs,
  },
  feedbackBtnLiked: {
    backgroundColor: colors.semantic.success + "33",
    borderWidth: 1,
    borderColor: colors.semantic.success + "66",
  },
  feedbackBtnDisliked: {
    backgroundColor: colors.semantic.error + "33",
    borderWidth: 1,
    borderColor: colors.semantic.error + "66",
  },
  feedbackBtnDimmed: {
    opacity: 0.4,
  },
  feedbackBtnText: {
    ...typography.label.sm,
    color: colors.text.secondary,
  },
  emptyState: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    gap: spacing.md,
  },
  emptyTitle: {
    ...typography.heading.sm,
    color: colors.text.primary,
  },
  emptySub: {
    ...typography.body.md,
    color: colors.text.secondary,
    textAlign: "center",
  },
  goHomeBtn: {
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    backgroundColor: colors.brand[600],
    borderRadius: radius.xl,
    ...shadow.md,
  },
  goHomeBtnText: {
    ...typography.label.md,
    color: colors.text.onBrand,
  },
  noRecs: {
    ...typography.body.md,
    color: colors.text.secondary,
    textAlign: "center",
    marginTop: spacing.xl,
  },
  tryAgainBtn: {
    backgroundColor: colors.brand[600],
    borderRadius: radius.xl,
    paddingVertical: isWeb ? 16 : spacing.md + 2,
    alignItems: "center",
    marginTop: spacing.lg,
    maxWidth: isWeb ? 400 : undefined,
    alignSelf: "center" as any,
    width: "100%",
    ...shadow.lg,
  },
  tryAgainText: {
    ...typography.label.lg,
    color: colors.text.onBrand,
  },
});
