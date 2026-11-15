import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { useColorScheme as useNativeWindColorScheme } from "nativewind";

import { cotton, type Material, materialForTheme, nylon } from "./material";

export type ThemeName = "dark" | "light";

const STORAGE_KEY = "synclook.theme";

/** Cotton opens the app. Settled in Phase 7 from the physical scene in
 *  PRODUCT.md rather than from preference: the shopper is standing at an open
 *  wardrobe, in a shop under overhead fluorescents, or by a window in daylight,
 *  where a near-black screen is a mirror. The direction contract's THESIS also
 *  refuses the near-black home by name — it is the arrangement this category
 *  always ships, and it is what the rejected build defaulted to. Both materials
 *  remain first-class and the switch is still the user's. */
const DEFAULT_THEME: ThemeName = "light";

interface ThemeContextValue {
  /** Active theme name */
  themeName: ThemeName;
  /** The material that theme is: grounds, ink, strokes. Read this rather than
   *  importing `cotton`/`nylon` directly, so a screen is never written against
   *  one material. */
  material: Material;
  /** Set the theme explicitly and persist the choice */
  setThemeName: (name: ThemeName) => void;
  /** Flip between the two themes */
  toggleTheme: () => void;
  /** False until the persisted preference has been read once, so the very
   *  first frame doesn't flash the default theme over a stored choice */
  isReady: boolean;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { setColorScheme } = useNativeWindColorScheme();
  const [themeName, setThemeNameState] = useState<ThemeName>(DEFAULT_THEME);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let initial: ThemeName = DEFAULT_THEME;
      try {
        const stored = await AsyncStorage.getItem(STORAGE_KEY);
        if (stored === "dark" || stored === "light") initial = stored;
      } catch {
        // No persisted preference (or storage unavailable) — fall back to default.
      }
      if (cancelled) return;
      setColorScheme(initial);
      setThemeNameState(initial);
      setIsReady(true);
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setThemeName = useCallback(
    (name: ThemeName) => {
      setThemeNameState(name);
      setColorScheme(name);
      AsyncStorage.setItem(STORAGE_KEY, name).catch(() => {});
    },
    [setColorScheme],
  );

  const toggleTheme = useCallback(() => {
    setThemeName(themeName === "dark" ? "light" : "dark");
  }, [themeName, setThemeName]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      themeName,
      material: materialForTheme[themeName],
      setThemeName,
      toggleTheme,
      isReady,
    }),
    [themeName, setThemeName, toggleTheme, isReady],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

/** THE COUNTER MATERIAL — Phase 8's decision, encoded in Phase 9.
 *
 *  The direction contract says the desktop rail is "a fixed left rail,
 *  cotton-white", which is literally true only in the nylon theme. Phase 8
 *  confirmed the working reading: the rail is always the *counter* material to
 *  the main plane. The rail is apparatus and the plane is the work, and
 *  countering them keeps the pair legible in both themes instead of making the
 *  rail true in one.
 *
 *  Everything inside this boundary — plates, screws, code lines, strokes —
 *  reads the counter material through the same `useTheme()` it always uses, so
 *  no component needs a second colour path. `themeName` is untouched, which
 *  keeps the switch, the persisted preference and NativeWind's `dark:` variant
 *  speaking about the page rather than about the rail.
 */
export function CounterMaterial({ children }: { children: React.ReactNode }) {
  const ctx = useTheme();
  const counter = ctx.themeName === "light" ? nylon : cotton;
  const value = useMemo<ThemeContextValue>(
    () => ({ ...ctx, material: counter }),
    [ctx, counter],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within a ThemeProvider");
  return ctx;
}
