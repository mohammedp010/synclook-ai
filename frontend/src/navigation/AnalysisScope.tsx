/** One read, visible from everywhere — Plan v2 Phase 9.
 *
 *  `useAnalysis` is product truth and is not edited. But it is a hook, so each
 *  caller gets its own state machine, and Phase 8's composition has two
 *  callers that must see the *same* run: the read surface, and the permanent
 *  `"SYSTEM STATUS"` plate in the desktop rail, which stands over the layers
 *  too. Two instances would make the rail report `"NO RUN YET"` while a read
 *  was visibly finished on the plane beside it — a status plate that lies.
 *
 *  So the hook is called exactly once, here, and shared. Nothing about its
 *  behaviour changes; this is a scope, not a wrapper. It also means opening
 *  `"THE WARDROBE"` and coming back does not discard a finished read, which is
 *  the flow continuity the layer decision assumed.
 */

import React, { createContext, useContext } from "react";

import { useAnalysis } from "../hooks/useAnalysis";

type Analysis = ReturnType<typeof useAnalysis>;

const AnalysisContext = createContext<Analysis | undefined>(undefined);

export function AnalysisScope({ children }: { children: React.ReactNode }) {
  const analysis = useAnalysis();
  return <AnalysisContext.Provider value={analysis}>{children}</AnalysisContext.Provider>;
}

export function useAnalysisScope(): Analysis {
  const ctx = useContext(AnalysisContext);
  if (!ctx) throw new Error("useAnalysisScope must be used within an AnalysisScope");
  return ctx;
}
