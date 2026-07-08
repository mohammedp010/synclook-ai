import React from "react";
import Svg, {
  Rect,
  Circle,
  Line,
  G,
  LinearGradient,
  Stop,
  Defs,
} from "react-native-svg";

interface WardrobeIllustrationProps {
  width?: number;
  height?: number;
}

export function WardrobeIllustration({
  width = 272,
  height = 220,
}: WardrobeIllustrationProps) {
  return (
    <Svg width={width} height={height} viewBox="0 0 272 220">
      <Defs>
        <LinearGradient id="bodyGrad" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#222238" />
          <Stop offset="1" stopColor="#1a1a2e" />
        </LinearGradient>
        <LinearGradient id="doorGrad" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#2a2a40" />
          <Stop offset="1" stopColor="#222238" />
        </LinearGradient>
        <LinearGradient id="purpleGrad" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor="#c4b5fd" />
          <Stop offset="1" stopColor="#7c3aed" />
        </LinearGradient>
      </Defs>

      <Rect x="8" y="18" width="256" height="188" rx="8"
        fill="url(#bodyGrad)" stroke="#2e2e4a" strokeWidth="1.5" />
      <Rect x="8" y="18" width="256" height="22" rx="8" fill="#2e2e4a" />
      <Rect x="8" y="32" width="256" height="8" fill="#2e2e4a" />
      <Rect x="28" y="200" width="16" height="14" rx="4" fill="#2e2e4a" />
      <Rect x="228" y="200" width="16" height="14" rx="4" fill="#2e2e4a" />
      <Rect x="12" y="44" width="120" height="158" rx="4"
        fill="url(#doorGrad)" stroke="#2e2e4a" strokeWidth="1" />
      <Rect x="140" y="44" width="120" height="158" rx="4"
        fill="url(#doorGrad)" stroke="#2e2e4a" strokeWidth="1" />
      <Line x1="136" y1="44" x2="136" y2="202" stroke="#2e2e4a" strokeWidth="2" />
      <Rect x="122" y="118" width="5" height="18" rx="2.5" fill="url(#purpleGrad)" />
      <Rect x="145" y="118" width="5" height="18" rx="2.5" fill="url(#purpleGrad)" />
      <Line x1="24" y1="72" x2="120" y2="72" stroke="#3a3a56" strokeWidth="1.5" />
      <G opacity={0.9}>
        <Circle cx="48" cy="70" r="2.5" fill="#8b5cf6" />
        <Circle cx="72" cy="70" r="2.5" fill="#a78bfa" />
        <Circle cx="96" cy="70" r="2.5" fill="#c4b5fd" />
        <Rect x="38" y="75" width="20" height="42" rx="3" fill="#7c3aed" opacity={0.7} />
        <Rect x="62" y="75" width="20" height="38" rx="3" fill="#ddd6fe" opacity={0.4} />
        <Rect x="86" y="75" width="20" height="44" rx="3" fill="#a78bfa" opacity={0.6} />
      </G>
      <Line x1="18" y1="130" x2="126" y2="130" stroke="#2e2e4a" strokeWidth="1.5" />
      <Rect x="22" y="134" width="46" height="14" rx="3" fill="#5b21b6" opacity={0.5} />
      <Rect x="72" y="134" width="34" height="14" rx="3" fill="#4c1d95" opacity={0.4} />
      <Rect x="22" y="152" width="80" height="12" rx="3" fill="#2e2e4a" />
      <Line x1="148" y1="72" x2="252" y2="72" stroke="#3a3a56" strokeWidth="1.5" />
      <G opacity={0.9}>
        <Circle cx="172" cy="70" r="2.5" fill="#8b5cf6" />
        <Circle cx="200" cy="70" r="2.5" fill="#c4b5fd" />
        <Circle cx="228" cy="70" r="2.5" fill="#a78bfa" />
        <Rect x="162" y="75" width="20" height="46" rx="3" fill="#6d28d9" opacity={0.6} />
        <Rect x="190" y="75" width="20" height="40" rx="3" fill="#5b21b6" opacity={0.5} />
        <Rect x="218" y="75" width="20" height="44" rx="3" fill="#c4b5fd" opacity={0.4} />
      </G>
      <Line x1="146" y1="130" x2="254" y2="130" stroke="#2e2e4a" strokeWidth="1.5" />
      <Rect x="150" y="134" width="42" height="14" rx="3" fill="#3a3a56" opacity={0.5} />
      <Rect x="196" y="134" width="30" height="14" rx="3" fill="#4c1d95" opacity={0.4} />
      <Rect x="150" y="152" width="96" height="12" rx="3" fill="#2e2e4a" />
      <Circle cx="234" cy="30" r="3" fill="#a78bfa" opacity={0.8} />
      <Circle cx="40" cy="30" r="2" fill="#8b5cf6" opacity={0.7} />
    </Svg>
  );
}
