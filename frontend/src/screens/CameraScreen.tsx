import React from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useNavigation } from "@react-navigation/native";
import { GlowBackground } from "../components/ui/GlowBackground";
import { AnimatedEntry } from "../components/ui/AnimatedEntry";
import { HangerIcon } from "../components/svg/HangerIcon";
import { colors, typography, spacing, radius, shadow, glass } from "../theme/tokens";

export default function CameraScreen() {
  const navigation = useNavigation<any>();

  return (
    <GlowBackground>
      <SafeAreaView style={styles.container} edges={["top", "left", "right"]}>
        <View style={styles.content}>
          <AnimatedEntry index={0}>
            <View style={styles.iconWrap}>
              <HangerIcon size={48} color={colors.brand[400]} />
            </View>
          </AnimatedEntry>
          <AnimatedEntry index={1}>
            <Text style={styles.title}>Camera</Text>
            <Text style={styles.sub}>
              Use the camera option on the Home screen to capture your clothing.
            </Text>
          </AnimatedEntry>
          <AnimatedEntry index={2}>
            <TouchableOpacity
              style={styles.btn}
              onPress={() => navigation.goBack()}
              activeOpacity={0.8}
            >
              <Text style={styles.btnText}>Go Back</Text>
            </TouchableOpacity>
          </AnimatedEntry>
        </View>
      </SafeAreaView>
    </GlowBackground>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    gap: spacing.md,
  },
  iconWrap: {
    ...glass.card,
    width: 80,
    height: 80,
    borderRadius: 40,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  title: {
    ...typography.heading.sm,
    color: colors.text.primary,
    textAlign: "center",
  },
  sub: {
    ...typography.body.md,
    color: colors.text.secondary,
    textAlign: "center",
    lineHeight: 22,
  },
  btn: {
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    backgroundColor: colors.brand[600],
    borderRadius: radius.xl,
    ...shadow.md,
  },
  btnText: { ...typography.label.md, color: colors.text.onBrand },
});
