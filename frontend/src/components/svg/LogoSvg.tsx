import React, { useEffect } from "react";
import Svg, {
  Path,
  Circle,
  Defs,
  LinearGradient,
  Stop,
  G,
} from "react-native-svg";
import Animated, {
  useAnimatedProps,
  useSharedValue,
  useAnimatedStyle,
} from "react-native-reanimated";
import { pulseLoop } from "../../utils/animations";

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

interface LogoSvgProps {
  size?: number;
  animated?: boolean;
}

export function LogoSvg({ size = 48, animated = true }: LogoSvgProps) {
  const pulse = useSharedValue(1);

  useEffect(() => {
    if (animated) {
      pulse.value = pulseLoop(0.85, 1.15, 2000);
    }
  }, [animated]);

  const animatedProps = useAnimatedProps(() => ({
    opacity: 0.2 + 0.2 * (pulse.value - 0.85) * 3.33,
    r: 18 * pulse.value,
  }));

  return (
    <Svg width={size} height={size} viewBox="0 0 64 64" fill="none">
      <Defs>
        <LinearGradient id="logoGrad" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor="#c4b5fd" />
          <Stop offset="1" stopColor="#7c3aed" />
        </LinearGradient>
        <LinearGradient id="glowGrad" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor="#a78bfa" stopOpacity="0.3" />
          <Stop offset="1" stopColor="#6d28d9" stopOpacity="0" />
        </LinearGradient>
      </Defs>

      {/* Glow ring */}
      <AnimatedCircle cx="32" cy="32" fill="url(#glowGrad)" animatedProps={animatedProps} />

      {/* Background circle */}
      <Circle cx="32" cy="32" r="28" fill="#1a1a2e" />
      <Circle cx="32" cy="32" r="27" stroke="url(#logoGrad)" strokeWidth="1.5" fill="none" />

      {/* Hanger shape */}
      <G>
        <Path
          d="M32 14 C32 14 32 18 32 20"
          stroke="#a78bfa"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <Circle cx="32" cy="13" r="2.5" fill="url(#logoGrad)" />
        <Path
          d="M32 20 C32 20 20 28 16 34 C14 37 16 40 20 40 L44 40 C48 40 50 37 48 34 C44 28 32 20 32 20Z"
          stroke="url(#logoGrad)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </G>

      {/* Accent sparkle dot */}
      <Circle cx="46" cy="20" r="3" fill="#c4b5fd" opacity={0.9} />
    </Svg>
  );
}
