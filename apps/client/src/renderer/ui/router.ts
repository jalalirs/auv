// Where somebody is, kept in the window's address and its history.
//
// The deck used to hold where you were in one piece of state: opening a run
// replaced the page, and there was no way back to the list you opened it
// from. Now every page has an address (#/runs, #/place?id=city_…), each move
// is a history entry, Back and Forward work (the mouse's side buttons, a
// trackpad swipe, Cmd-[ and Cmd-]), and a page you return to is scrolled to
// where you left it.

import { useCallback, useEffect, useRef, useState } from "react";

/** A page and what it is of: every value a string, so it fits an address. */
export type Address = { page: string } & Record<string, string | undefined>;

export function toHash(where: Address): string {
  const { page, ...rest } = where;
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(rest)) if (v !== undefined && v !== "") query.set(k, v);
  const q = query.toString();
  return `#/${page}${q ? `?${q}` : ""}`;
}

export function fromHash(hash: string): Address | undefined {
  const found = hash.match(/^#\/([a-z-]+)(?:\?(.*))?$/);
  if (!found) return undefined;
  const where: Address = { page: found[1]! };
  for (const [k, v] of new URLSearchParams(found[2] ?? "")) where[k] = v;
  return where;
}

type Entry = { depth: number };

/** Scroll positions by address, for the pages somebody comes back to. */
const scrolled = new Map<string, number>();

/**
 * The current address, and how to move. `scroller` is the element whose
 * scroll is kept per page. `known` says whether an address read from the
 * window is one this application has (a stale bookmark falls back to `home`).
 */
export function useAddress<W extends Address>(home: W, known: (where: Address) => boolean, scroller: () => HTMLElement | null): {
  where: W;
  go: (to: W, options?: { replace?: boolean }) => void;
  back: (fallback: W) => void;
  canGoBack: boolean;
} {
  const read = useCallback((): W => {
    const where = fromHash(window.location.hash);
    return (where && known(where) ? where : home) as W;
  }, [home, known]);
  const [where, setWhere] = useState<W>(read);
  const [depth, setDepth] = useState<number>(() => (window.history.state as Entry | null)?.depth ?? 0);
  const current = useRef(window.location.hash);

  useEffect(() => {
    if (!window.location.hash || !fromHash(window.location.hash)) {
      window.history.replaceState({ depth: 0 } satisfies Entry, "", toHash(home));
      current.current = window.location.hash;
    }
    const moved = () => {
      const el = scroller();
      if (el) scrolled.set(current.current, el.scrollTop);
      current.current = window.location.hash;
      setDepth((window.history.state as Entry | null)?.depth ?? 0);
      setWhere(read());
    };
    window.addEventListener("popstate", moved);
    // Cmd-[ and Cmd-] (Alt and the arrows elsewhere), as in every browser.
    const keys = (e: KeyboardEvent) => {
      const back = (e.metaKey && e.key === "[") || (e.altKey && e.key === "ArrowLeft");
      const forward = (e.metaKey && e.key === "]") || (e.altKey && e.key === "ArrowRight");
      const typing = e.target instanceof HTMLElement && e.target.closest("input, textarea, select, [contenteditable]");
      if (typing) return;
      if (back) { e.preventDefault(); window.history.back(); }
      if (forward) { e.preventDefault(); window.history.forward(); }
    };
    window.addEventListener("keydown", keys);
    // The mouse's side buttons.
    const buttons = (e: MouseEvent) => {
      if (e.button === 3) { e.preventDefault(); window.history.back(); }
      if (e.button === 4) { e.preventDefault(); window.history.forward(); }
    };
    window.addEventListener("mouseup", buttons);
    return () => {
      window.removeEventListener("popstate", moved);
      window.removeEventListener("keydown", keys);
      window.removeEventListener("mouseup", buttons);
    };
  }, [home, read, scroller]);

  // A page come back to is scrolled where it was left; a new one starts at the top.
  useEffect(() => {
    const el = scroller();
    if (!el) return;
    const at = scrolled.get(window.location.hash) ?? 0;
    requestAnimationFrame(() => { el.scrollTop = at; });
  }, [where, scroller]);

  const go = useCallback((to: W, options?: { replace?: boolean }) => {
    const hash = toHash(to);
    if (hash === window.location.hash) return;
    const el = scroller();
    if (el) scrolled.set(window.location.hash, el.scrollTop);
    scrolled.delete(hash);
    const next = options?.replace ? depth : depth + 1;
    if (options?.replace) window.history.replaceState({ depth: next } satisfies Entry, "", hash);
    else window.history.pushState({ depth: next } satisfies Entry, "", hash);
    current.current = hash;
    setDepth(next);
    setWhere(to);
  }, [depth, scroller]);

  const back = useCallback((fallback: W) => {
    if (depth > 0) window.history.back();
    else go(fallback, { replace: true });
  }, [depth, go]);

  return { where, go, back, canGoBack: depth > 0 };
}
