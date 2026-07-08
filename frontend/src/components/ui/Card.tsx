import React from "react";
import { View, StyleSheet, type ViewProps } from "react-native";
import { colors, radius, shadow, glass } from "../../theme/tokens";


interface Props extends ViewProps {
  elevated?: boolean;
}

export function Card({ children, elevated = false, style, ...rest }: Props) {
  return (
    <View
      style={[styles.card, elevated && styles.elevated, style]}
      {...rest}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    ...glass.card,
    borderRadius: radius.xl,
    ...shadow.sm,
  },
  elevated: {
    ...glass.elevated,
    ...shadow.md,
  },
});
