/** @type {import('tailwindcss').Config} */
// darkMode: "class" is required by NativeWind v4's useColorScheme().setColorScheme()
// (see src/theme/ThemeProvider.tsx) — without it, NativeWind throws
// "Unable to manually set color scheme without using darkMode: class" the
// moment the app tries to apply the persisted/explicit theme choice.
//
// This file is plain CommonJS and can't import a TypeScript module, so
// everything under theme.extend is hand-copied and must stay byte-for-byte in
// sync with its source. Change them together or NativeWind and StyleSheet
// drift apart silently.
//
//   fontFamily / fontSize            <-  src/theme/type.ts     (Phase 6, landed)
//   colors / spacing / borderWidth   <-  src/theme/material.ts (Phase 7, landed)
module.exports = {
  darkMode: "class",
  content: ["./App.{js,jsx,ts,tsx}", "./src/**/*.{js,jsx,ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      // src/theme/type.ts -> families
      fontFamily: {
        stencil: ["BigShouldersDisplay_900Black"],
        "stencil-mid": ["BigShouldersDisplay_700Bold"],
        plate: ["MartianMono_400Regular"],
        "plate-bold": ["MartianMono_700Bold"],
        text: ["Archivo_400Regular"],
        "text-mid": ["Archivo_500Medium"],
      },
      // src/theme/type.ts -> sizes. Two ramps: display steps ~1.385, text ~1.1.
      // The display ramp stops at 80 because the vision pass's longest token,
      // "STREETWEAR", sets 446pt there and a phone has 350pt to give.
      fontSize: {
        d1: "22px",
        d2: "30px",
        d3: "42px",
        d4: "58px",
        d5: "80px",
        t1: "10px",
        t2: "11px",
        t3: "12px",
        t4: "13px",
        t5: "15px",
        t6: "17px",
      },
      // src/theme/material.ts -> cotton, nylon, tag, hazard, dye.
      //
      // The two materials are named rather than folded into one semantic token
      // set, because the pair is not an inversion: a plane separates by tone on
      // cotton and by stroke on nylon. A screen writes the pair explicitly —
      // `bg-cotton-ground dark:bg-nylon-ground` — which keeps the difference
      // visible in the markup instead of hiding it behind one name.
      colors: {
        cotton: {
          ground: "#FFFFFF",
          label: "#E6E6E6",
          well: "#D2D2D2",
          ink: "#0A0A0A",
          "ink-dim": "#4C4C4C",
          stroke: "#4C4C4C",
          "stroke-heavy": "#0A0A0A",
        },
        nylon: {
          ground: "#1A1A1A",
          label: "#2A2A2A",
          well: "#101010",
          ink: "#FFFFFF",
          "ink-dim": "#BABABA",
          stroke: "#BABABA",
          "stroke-heavy": "#FFFFFF",
        },
        // The single system hue. A field in both materials; near-black prints
        // on it. `ink-on-nylon` is the one sanctioned use of orange as ink and
        // only ever on the nylon ground (5.56:1; on cotton it is 3.13:1).
        tag: {
          field: "#FF5A00",
          ink: "#0A0A0A",
          "ink-on-nylon": "#FF5A00",
        },
        // Material-invariant. A verifier flag and nothing else.
        hazard: {
          a: "#0A0A0A",
          b: "#FFFFFF",
        },
        // Content, not brand. The garment's own dye, from the closed `Color`
        // set in backend/schemas/clothing.py. `other` is deliberately absent —
        // the pipeline could not name that colour, so it prints struck.
        dye: {
          black: "#17161A",
          white: "#F6F3EC",
          red: "#C1272D",
          blue: "#1F5FA9",
          navy: "#16233F",
          green: "#2E7D4F",
          yellow: "#E8B310",
          orange: "#D2601A",
          pink: "#D94F82",
          purple: "#6B3FA0",
          brown: "#6B4A2F",
          grey: "#909093",
          beige: "#D6C3A5",
          cream: "#EFE4CC",
          maroon: "#6E1C2B",
          olive: "#5E6033",
          teal: "#16706E",
        },
      },
      // src/theme/material.ts -> space. Additive: each step is the sum of the
      // two before it, on a stencil pitch of 5. Dense at the bottom for the
      // margins, hard jumps at the top for the zones. Deliberately not
      // 4/8/16/24/32/48/64 — that ladder is the rejected build's.
      spacing: {
        s1: "5px",
        s2: "10px",
        s3: "15px",
        s4: "25px",
        s5: "40px",
        s6: "65px",
        s7: "105px",
        s8: "170px",
      },
      // src/theme/material.ts -> surface. No radius scale: every corner in this
      // world is square, which is a rule rather than a token.
      borderWidth: {
        hairline: "1px",
        rule: "2px",
      },
    },
  },
  plugins: [],
};
