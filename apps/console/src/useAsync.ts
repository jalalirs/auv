import { useEffect, useState } from "react";

import { Refused } from "./api/client.js";

/** What a screen knows about something it asked the platform for. */
export type Asked<T> =
  | { state: "asking" }
  | { state: "answered"; value: T }
  | { state: "refused"; refusal: Refused }
  | { state: "broken"; error: Error };

/**
 * Ask the platform for something, and keep the refusal if it refuses.
 *
 * A refusal is not an error: it is the platform saying something true about
 * what the caller may know, and screens show it as such rather than as a
 * failure of theirs.
 */
export function useAsked<T>(ask: () => Promise<T>, deps: unknown[]): Asked<T> {
  const [asked, setAsked] = useState<Asked<T>>({ state: "asking" });

  useEffect(() => {
    let current = true;
    setAsked({ state: "asking" });
    ask()
      .then((value) => { if (current) setAsked({ state: "answered", value }); })
      .catch((error: unknown) => {
        if (!current) return;
        if (error instanceof Refused) setAsked({ state: "refused", refusal: error });
        else setAsked({ state: "broken", error: error as Error });
      });
    return () => { current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return asked;
}
