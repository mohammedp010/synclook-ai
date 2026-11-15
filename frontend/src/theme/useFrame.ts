/** The frame — Plan v2 Phase 9.
 *
 *  One route graph, two compositions (Phase 8). This is the only place the
 *  build asks which frame it is in, so a screen never re-derives the boundary
 *  from a raw width and the two answers can never disagree.
 *
 *  v1's adaptive story was a `maxWidth` cap in six screens and a
 *  `src/utils/responsive.ts` of scale factors; both are deleted. A cap is not
 *  a composition.
 */

import { useCallback, useState } from "react";
import { useWindowDimensions, type LayoutChangeEvent } from "react-native";

import { grid } from "./material";

export type FrameName = "phone" | "tablet" | "desktop";

/** Tablet begins where a phone's single sequence stops being the honest
 *  reading — wide enough for three plates across, too narrow for a fixed rail
 *  plus a split plane. Phase 12 tunes it; the boundary lives here. */
const TABLET_FROM = 600;

export interface Frame {
  width: number;
  name: FrameName;
  isPhone: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  /** Page margin for this frame. */
  margin: number;
  /** Outfit grid columns. */
  cells: number;
  /** Fixed left rail width, 0 where there is no rail. */
  rail: number;
}

export function useFrame(): Frame {
  const { width } = useWindowDimensions();

  const name: FrameName =
    width >= grid.desktopFrom ? "desktop" : width >= TABLET_FROM ? "tablet" : "phone";

  return {
    width,
    name,
    isPhone: name === "phone",
    isTablet: name === "tablet",
    isDesktop: name === "desktop",
    margin: name === "phone" ? grid.marginPhone : grid.marginDesktop,
    cells: name === "desktop" ? grid.cellsDesktop : name === "tablet" ? 3 : grid.cellsPhone,
    rail: name === "desktop" ? grid.rail : 0,
  };
}

/** Square cell edge for a grid of `cells` columns inside `available` points.
 *  The cell is square by rule (material.ts `grid`), so the count is the
 *  frame's and the size is a consequence — which is what stops a plate from
 *  wrapping a hundred points narrower than it was composed for. */
export function cellSize(available: number, cells: number): number {
  return Math.floor((available - grid.gutter * (cells - 1)) / cells);
}

/** The grid's real width, measured rather than derived.
 *
 *  `useWindowDimensions()` reports the window, which on the web includes the
 *  scrollbar the page is about to grow. Composing a two-up grid from that
 *  figure overflows its container by ~15pt and every cell wraps to one-up —
 *  caught on the phone frame, where the outfit stacked in a single column and
 *  the density the composition depends on collapsed. Measuring the container
 *  itself is the only figure that is true on both platforms.
 *
 *  Returns `null` until the first layout pass, so a caller can hold the grid
 *  back for one frame rather than paint it at the wrong size and reflow. */
export function useMeasuredWidth(): [number | null, (e: LayoutChangeEvent) => void] {
  const [width, setWidth] = useState<number | null>(null);
  const onLayout = useCallback((e: LayoutChangeEvent) => {
    const next = Math.floor(e.nativeEvent.layout.width);
    setWidth((cur) => (cur === next ? cur : next));
  }, []);
  return [width, onLayout];
}
