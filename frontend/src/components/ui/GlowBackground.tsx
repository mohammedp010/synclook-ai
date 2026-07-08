import React, { useEffect } from "react";
import { View, StyleSheet, Platform } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
} from "react-native-reanimated";
import { pulseLoop } from "../../utils/animations";

const isWeb = Platform.OS === "web";

interface Props {
  children: React.ReactNode;
}

export function GlowBackground({ children }: Props) {
  const opacity1 = useSharedValue(0.12);
  const opacity2 = useSharedValue(0.08);

  useEffect(() => {
    opacity1.value = pulseLoop(0.08, 0.18, 4000);
    opacity2.value = pulseLoop(0.05, 0.12, 5000);
  }, []);

  const glow1Style = useAnimatedStyle(() => ({
    opacity: opacity1.value,
  }));

  const glow2Style = useAnimatedStyle(() => ({
    opacity: opacity2.value,
  }));

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.glow1, glow1Style]} />
      <Animated.View style={[styles.glow2, glow2Style]} />
      {isWeb && <Animated.View style={[styles.glow3, glow1Style]} />}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0f0f14",
    overflow: "hidden",
  },
  glow1: {
    position: "absolute",
    top: isWeb ? -150 : -100,
    right: isWeb ? "10%" as any : -80,
    width: isWeb ? 500 : 300,
    height: isWeb ? 500 : 300,
    borderRadius: isWeb ? 250 : 150,
    backgroundColor: "#8b5cf6",
  },
  glow2: {
    position: "absolute",
    bottom: isWeb ? -100 : -60,
    left: isWeb ? -150 : -100,
    width: isWeb ? 450 : 250,
    height: isWeb ? 450 : 250,
    borderRadius: isWeb ? 225 : 125,
    backgroundColor: "#6d28d9",
  },
  glow3: {
    position: "absolute",
    top: "50%" as any,
    left: "50%" as any,
    width: 400,
    height: 400,
    borderRadius: 200,
    backgroundColor: "#7c3aed",
    transform: [{ translateX: -200 }, { translateY: -200 }],
  },
});
