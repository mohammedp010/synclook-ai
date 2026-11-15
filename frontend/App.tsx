import React from "react";
import { View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { useFonts } from "expo-font";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { RootNavigator } from "./src/navigation/RootNavigator";
import { ThemeProvider, useTheme } from "./src/theme/ThemeProvider";
import { fontAssets } from "./src/theme/type";

/** The app entry — Plan v2 Phase 9.
 *
 *  Phase 6's type specimen was mounted here and is now deleted, as both Phase 6
 *  and Phase 7 said it would be when the screens landed. Its evidence lives in
 *  `.impeccable/review/phase6-type/` and `phase7-material/`.
 *
 *  Nothing renders until the fonts and the persisted material preference are
 *  both in. Two things depend on that: this world is set in three faces whose
 *  fallbacks look nothing like them, so a first frame in the system sans would
 *  be a different design; and the material is persisted, so painting cotton
 *  before nylon loads is a flash of the wrong world. The gate is a held ground
 *  in the default material, not a spinner — it lasts one or two frames and a
 *  spinner for that is theatre.
 */
function Shell() {
  const { isReady, material } = useTheme();
  const [fontsLoaded] = useFonts(fontAssets);

  if (!fontsLoaded || !isReady) {
    return <View style={{ flex: 1, backgroundColor: material.ground }} />;
  }

  return (
    <>
      <StatusBarForMaterial />
      <RootNavigator />
    </>
  );
}

/** The status bar is part of the material, not a platform default: ink-on-
 *  cotton reads dark, ink-on-nylon reads light. */
function StatusBarForMaterial() {
  const { themeName } = useTheme();
  return <StatusBar style={themeName === "dark" ? "light" : "dark"} />;
}

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <ThemeProvider>
          <Shell />
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
