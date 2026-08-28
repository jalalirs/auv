import { useCallback, useEffect, useState } from "react";
import { Refused } from "@coral-city/client";

/** What a screen knows about something it asked the platform for. */
export interface Asked<T> {
  loading: boolean;
  value?: T;
  /** refusal is set when the platform declined, which is often the answer. */
  refusal?: Refused;
  error?: Error;
  reload: () => void;
}

/**
 * useAsked fetches something and keeps the platform's refusal rather than
 * flattening it into a generic error.
 *
 * A refusal is frequently the most informative thing a screen can show — it
 * says whether a place is absent or merely closed — so it is not treated as a
 * fault.
 */
export function useAsked<T>(ask: () => Promise<T>, dependencies: unknown[]): Asked<T> {
  const [state, setState] = useState<Omit<Asked<T>, "reload">>({ loading: true });
  const [attempt, setAttempt] = useState(0);

  // The caller's closure changes every render; the dependency list is what
  // decides when to ask again.
  const run = useCallback(ask, dependencies);

  useEffect(() => {
    let current = true;
    setState({ loading: true });
    run()
      .then((value) => {
        if (current) setState({ loading: false, value });
      })
      .catch((error: unknown) => {
        if (!current) return;
        if (error instanceof Refused) {
          setState({ loading: false, refusal: error });
        } else {
          setState({ loading: false, error: error as Error });
        }
      });
    return () => {
      current = false;
    };
  }, [run, attempt]);

  return { ...state, reload: () => setAttempt((count) => count + 1) };
}
