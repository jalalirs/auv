// The runs flown under several conditions at once. Asking for one is New
// run's; reading one is Run.tsx's, the same page as any run. This is the list.

import { useCallback, useEffect, useState } from "react";

import type { Platform, Sweep } from "@coral-city/api";

import type { Held } from "./Deck.js";

/** The institution's sweeps, newest first, undefined until the first answer.
 *  Kept fresh while somebody looks: they fly for hours and the counts move. */
export function useSweeps(platform: Platform, held: Held): Sweep[] | undefined {
  const [sweeps, setSweeps] = useState<Sweep[] | undefined>();
  const read = useCallback(() => {
    if (held.institution === undefined) { setSweeps([]); return; }
    void platform.sweepsOf(held.institution.id).then(setSweeps).catch(() => setSweeps((was) => was ?? []));
  }, [platform, held.institution]);
  useEffect(read, [read]);
  useEffect(() => {
    const again = setInterval(read, 15_000);
    return () => clearInterval(again);
  }, [read]);
  return sweeps;
}
