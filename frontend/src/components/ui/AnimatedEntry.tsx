import React, { useEffect } from "react";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withDelay,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { SPRING_SNAPPY } from "../../utils/animations";

interface Props {
  children: React.ReactNode;
  index?: number;
  delay?: number;
  direction?: "up" | "down" | "left" | "right";
}

export function AnimatedEntry({
  children,
  index = 0,
  delay = 0,
  direction = "up",
}: Props) {
  const opacity = useSharedValue(0);
  const translate = useSharedValue(
    direction === "up" || direction === "left" ? 30 : -30
  );

  useEffect(() => {
    const totalDelay = delay + index * 100;
    opacity.value = withDelay(totalDelay, withTiming(1, { duration: 350 }));
    translate.value = withDelay(totalDelay, withSpring(0, SPRING_SNAPPY));
  }, []);

  const style = useAnimatedStyle(() => {
    const isVertical = direction === "up" || direction === "down";
    return {
      opacity: opacity.value,
      transform: [
        isVertical
          ? { translateY: translate.value }
          : { translateX: translate.value },
      ],
    };
  });

  return <Animated.View style={style}>{children}</Animated.View>;
}
