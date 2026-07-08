import React, { useEffect } from "react";
import Svg, { Path, Defs, LinearGradient, Stop } from "react-native-svg";
import Animated, {
  useSharedValue,
  useAnimatedProps,
  withRepeat,
  withTiming,
  Easing,
  interpolate,
} from "react-native-reanimated";

const AnimatedPath = Animated.createAnimatedComponent(Path);

interface Props {
  width?: number;
  height?: number;
}

export function AnalyzingWave({ width = 320, height = 80 }: Props) {
  const progress = useSharedValue(0);

  useEffect(() => {
    progress.value = withRepeat(
      withTiming(1, { duration: 2000, easing: Easing.linear }),
      -1,
      false
    );
  }, []);

  const animatedProps1 = useAnimatedProps(() => {
    const shift = interpolate(progress.value, [0, 1], [0, 60]);
    return {
      d: `M${-60 + shift} 40 C${-40 + shift} 20, ${-20 + shift} 60, ${0 + shift} 40 C${20 + shift} 20, ${40 + shift} 60, ${60 + shift} 40 C${80 + shift} 20, ${100 + shift} 60, ${120 + shift} 40 C${140 + shift} 20, ${160 + shift} 60, ${180 + shift} 40 C${200 + shift} 20, ${220 + shift} 60, ${240 + shift} 40 C${260 + shift} 20, ${280 + shift} 60, ${300 + shift} 40 C${320 + shift} 20, ${340 + shift} 60, ${360 + shift} 40`,
    };
  });

  const animatedProps2 = useAnimatedProps(() => {
    const shift = interpolate(progress.value, [0, 1], [30, 90]);
    return {
      d: `M${-60 + shift} 40 C${-40 + shift} 55, ${-20 + shift} 25, ${0 + shift} 40 C${20 + shift} 55, ${40 + shift} 25, ${60 + shift} 40 C${80 + shift} 55, ${100 + shift} 25, ${120 + shift} 40 C${140 + shift} 55, ${160 + shift} 25, ${180 + shift} 40 C${200 + shift} 55, ${220 + shift} 25, ${240 + shift} 40 C${260 + shift} 55, ${280 + shift} 25, ${300 + shift} 40 C${320 + shift} 55, ${340 + shift} 25, ${360 + shift} 40`,
    };
  });

  return (
    <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <Defs>
        <LinearGradient id="waveGrad1" x1="0" y1="0" x2="1" y2="0">
          <Stop offset="0" stopColor="#a78bfa" stopOpacity="0.8" />
          <Stop offset="0.5" stopColor="#7c3aed" stopOpacity="1" />
          <Stop offset="1" stopColor="#a78bfa" stopOpacity="0.8" />
        </LinearGradient>
        <LinearGradient id="waveGrad2" x1="0" y1="0" x2="1" y2="0">
          <Stop offset="0" stopColor="#c4b5fd" stopOpacity="0.4" />
          <Stop offset="0.5" stopColor="#8b5cf6" stopOpacity="0.6" />
          <Stop offset="1" stopColor="#c4b5fd" stopOpacity="0.4" />
        </LinearGradient>
      </Defs>
      <AnimatedPath
        animatedProps={animatedProps2}
        stroke="url(#waveGrad2)"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />
      <AnimatedPath
        animatedProps={animatedProps1}
        stroke="url(#waveGrad1)"
        strokeWidth="3"
        fill="none"
        strokeLinecap="round"
      />
    </Svg>
  );
}
