import React from "react";
import { NavigationContainer, DefaultTheme } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import {
  useFonts,
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
} from "@expo-google-fonts/inter";
import { SpaceGrotesk_700Bold } from "@expo-google-fonts/space-grotesk";

import HomeScreen from "./src/screens/HomeScreen";
import LandingScreen from "./src/screens/LandingScreen";
import AnalysisScreen from "./src/screens/AnalysisScreen";
import ResultsScreen from "./src/screens/ResultsScreen";
import CameraScreen from "./src/screens/CameraScreen";

export type RootStackParamList = {
  Landing: undefined;
  Home: undefined;
  Analysis: { imageUri: string };
  Results: undefined;
  Camera: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

const DarkTheme = {
  ...DefaultTheme,
  dark: true,
  colors: {
    ...DefaultTheme.colors,
    primary: "#8b5cf6",
    background: "#0f0f14",
    card: "#1a1a2e",
    text: "#f8fafc",
    border: "#222238",
    notification: "#ff6b6b",
  },
};

export default function App() {
  const [fontsLoaded] = useFonts({
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
    SpaceGrotesk_700Bold,
  });

  if (!fontsLoaded) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <NavigationContainer theme={DarkTheme}>
        <StatusBar style="light" />
        <Stack.Navigator
          initialRouteName="Landing"
          screenOptions={{
            headerShown: false,
            animation: "slide_from_right",
            contentStyle: { backgroundColor: "#0f0f14" },
          }}
        >
          <Stack.Screen
            name="Landing"
            component={LandingScreen}
            options={{ animation: "fade" }}
          />
          <Stack.Screen name="Home" component={HomeScreen} />
          <Stack.Screen
            name="Analysis"
            component={AnalysisScreen}
            options={{ animation: "fade_from_bottom" }}
          />
          <Stack.Screen name="Results" component={ResultsScreen} />
          <Stack.Screen name="Camera" component={CameraScreen} />
        </Stack.Navigator>
      </NavigationContainer>
    </GestureHandlerRootView>
  );
}
