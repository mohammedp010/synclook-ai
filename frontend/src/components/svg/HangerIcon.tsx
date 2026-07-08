import React from "react";
import Svg, { Path, Defs, LinearGradient, Stop } from "react-native-svg";

interface Props {
  size?: number;
  color?: string;
}

export function HangerIcon({ size = 24, color = "#a78bfa" }: Props) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <Defs>
        <LinearGradient id="hangerGrad" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor="#c4b5fd" />
          <Stop offset="1" stopColor={color} />
        </LinearGradient>
      </Defs>
      {/* Hook */}
      <Path
        d="M12 3 C12 3 12 6 12 7.5"
        stroke="url(#hangerGrad)"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <Path
        d="M12 3 C12.5 3 14 3.5 14 5 C14 6.5 12 7.5 12 7.5"
        stroke="url(#hangerGrad)"
        strokeWidth="1.5"
        strokeLinecap="round"
        fill="none"
      />
      {/* Bar */}
      <Path
        d="M12 7.5 C12 7.5 4 13 2.5 16 C1.5 18 3 20 5 20 L19 20 C21 20 22.5 18 21.5 16 C20 13 12 7.5 12 7.5Z"
        stroke="url(#hangerGrad)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </Svg>
  );
}
