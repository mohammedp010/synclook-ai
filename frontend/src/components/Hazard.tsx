/** Hazard tape — Plan v2 Phase 9.
 *
 *  Reserved for one thing and one thing only: a claim the `VerifierAgent`
 *  flagged, which reaches the frontend as an entry in
 *  `StreamAnalysisResult.errors` or as a stream warning. The HONEST RISK in
 *  the direction contract is that this becomes costume; it stays real by
 *  never being reachable except from that data.
 *
 *  Material-invariant black on white in both themes, because it is the same
 *  physical tape whichever garment it is stuck to, and because a pattern
 *  survives greyscale and colour-blindness where a hue does not.
 */

import React from "react";
import { View } from "react-native";
import Svg, { Defs, Pattern, Rect } from "react-native-svg";

import { hazard } from "../theme/material";

let seq = 0;

export function Hazard({ height = hazard.band }: { height?: number }) {
  const id = React.useMemo(() => `hz${seq++}`, []);
  const s = hazard.stripe;

  return (
    <View style={{ height, width: "100%" }} accessibilityRole="image" accessibilityLabel="Flagged by the verifier">
      <Svg width="100%" height={height}>
        <Defs>
          <Pattern
            id={id}
            width={s * 2}
            height={s * 2}
            patternUnits="userSpaceOnUse"
            patternTransform={`rotate(${-hazard.angle})`}
          >
            <Rect x={0} y={0} width={s * 2} height={s * 2} fill={hazard.b} />
            <Rect x={0} y={0} width={s} height={s * 2} fill={hazard.a} />
          </Pattern>
        </Defs>
        <Rect x={0} y={0} width="100%" height={height} fill={`url(#${id})`} />
      </Svg>
    </View>
  );
}
