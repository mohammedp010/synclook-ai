import React, { useCallback } from "react";
import {
  Text,
  StyleSheet,
  ActivityIndicator,
  type ViewStyle,
} from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
} from "react-native-reanimated";
import { Gesture, GestureDetector } from "react-native-gesture-handler";
import { colors, typography, radius, spacing, shadow } from "../../theme/tokens";
import { pressIn, pressOut } from "../../utils/animations";

interface Props {
  label: string;
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  disabled?: boolean;
  onPress?: () => void;
  style?: ViewStyle;
}

export function Button({
  label,
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  onPress,
  style,
}: Props) {
  const scale = useSharedValue(1);

  const gesture = Gesture.Tap()
    .enabled(!(disabled || loading))
    .onBegin(() => { scale.value = pressIn(); })
    .onFinalize(() => { scale.value = pressOut(); })
    .onEnd(() => { onPress?.(); });

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const containerStyle = [
    styles.base,
    styles[`size_${size}`],
    styles[`variant_${variant}`],
    (disabled || loading) && styles.disabled,
    style,
  ];

  return (
    <GestureDetector gesture={gesture}>
      <Animated.View style={[containerStyle, animStyle]}>
        {loading ? (
          <ActivityIndicator
            size="small"
            color={variant === "primary" ? colors.text.onBrand : colors.brand[400]}
          />
        ) : (
          <Text
            style={[
              styles.label,
              variant === "secondary" && styles.label_secondary,
              variant === "ghost" && styles.label_ghost,
              size === "sm" && styles.labelSize_sm,
              size === "lg" && styles.labelSize_lg,
            ]}
          >
            {label}
          </Text>
        )}
      </Animated.View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.lg,
  },
  size_sm: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, minHeight: 36 },
  size_md: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, minHeight: 48 },
  size_lg: { paddingHorizontal: spacing.xl, paddingVertical: spacing.md + 4, minHeight: 56 },

  variant_primary: {
    backgroundColor: colors.brand[600],
    ...shadow.md,
  },
  variant_secondary: {
    backgroundColor: "transparent",
    borderWidth: 1.5,
    borderColor: colors.brand[500],
  },
  variant_ghost: { backgroundColor: "transparent" },

  disabled: { opacity: 0.5 },

  label: { ...typography.label.md, color: colors.text.onBrand },
  label_secondary: { color: colors.brand[400] },
  label_ghost: { color: colors.brand[400] },

  labelSize_sm: { ...typography.label.sm },
  labelSize_md: { ...typography.label.md },
  labelSize_lg: { ...typography.label.lg },
});
