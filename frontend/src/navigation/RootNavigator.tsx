/** The navigator — Plan v2 Phase 9, mounting Phase 8's route graph.
 *
 *  Three routes where v1 had six plus a bottom tab bar. `Read` is the working
 *  surface; `"THE WARDROBE"` and `"PREVIOUS READS"` are layers over it.
 *
 *  THE LAYERS ARE OPAQUE STACK SCREENS THAT DRAW THEIR OWN RAIL, not
 *  `transparentModal` cards. The contract's requirement is that the rail stays
 *  standing while a layer is open, and that is satisfied by composition: each
 *  layer renders the same `Rail` with its own zone marked active, so the
 *  apparatus is continuous across the boundary and only the plane changes.
 *  Doing it with a transparent modal would put the whole thing at the mercy of
 *  `react-native-screens`' web backend for the one property the design
 *  actually depends on. Phase 11 owns how the change is *cut*; this phase owns
 *  that nothing about the composition moves when it happens.
 *
 *  Header is off everywhere. There is no place in this world for a platform
 *  title bar: the zone head is the title, it is set in the page's own display
 *  face, and it says both where you are and what state the zone is in.
 */

import React from "react";
import { NavigationContainer, type LinkingOptions } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import { PreviousReadsLayer } from "../screens/PreviousReadsLayer";
import { ReadScreen } from "../screens/ReadScreen";
import { WardrobeLayer } from "../screens/WardrobeLayer";
import { useTheme } from "../theme/ThemeProvider";
import { AnalysisScope } from "./AnalysisScope";
import { linkingConfig, type RootStackParamList } from "./routes";

const Stack = createNativeStackNavigator<RootStackParamList>();

const linking: LinkingOptions<RootStackParamList> = {
  prefixes: [],
  config: linkingConfig as LinkingOptions<RootStackParamList>["config"],
};

export function RootNavigator() {
  const { material: m, themeName } = useTheme();

  /** The navigator's own theme exists only so the container's background
   *  matches the material behind the plane — a white flash between screens in
   *  nylon would be the one uncontrolled surface in the build. */
  const navTheme = React.useMemo(
    () => ({
      dark: themeName === "dark",
      colors: {
        primary: m.ink,
        background: m.ground,
        card: m.ground,
        text: m.ink,
        border: m.stroke,
        notification: m.ink,
      },
      fonts: {
        regular: { fontFamily: "Archivo_400Regular", fontWeight: "400" as const },
        medium: { fontFamily: "Archivo_500Medium", fontWeight: "500" as const },
        bold: { fontFamily: "Archivo_500Medium", fontWeight: "700" as const },
        heavy: { fontFamily: "BigShouldersDisplay_900Black", fontWeight: "900" as const },
      },
    }),
    [m, themeName],
  );

  return (
    <NavigationContainer linking={linking} theme={navTheme}>
      <AnalysisScope>
        <Stack.Navigator
          initialRouteName="Read"
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: m.ground },
            animation: "fade",
          }}
        >
          <Stack.Screen name="Read" component={ReadScreen} />
          <Stack.Screen name="Wardrobe" component={WardrobeLayer} />
          <Stack.Screen name="PreviousReads" component={PreviousReadsLayer} />
        </Stack.Navigator>
      </AnalysisScope>
    </NavigationContainer>
  );
}
