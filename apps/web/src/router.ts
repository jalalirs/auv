import { useCallback, useEffect, useState } from "react";

/**
 * A small router.
 *
 * The application has a handful of screens addressed by path, and nothing here
 * needs nested layouts, loaders, or code splitting. A dependency would be more
 * to understand than the forty lines it replaced.
 */

export function usePath(): string {
  const [path, setPath] = useState(() => window.location.pathname);

  useEffect(() => {
    const onNavigate = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onNavigate);
    window.addEventListener("coral:navigate", onNavigate);
    return () => {
      window.removeEventListener("popstate", onNavigate);
      window.removeEventListener("coral:navigate", onNavigate);
    };
  }, []);

  return path;
}

export function navigate(to: string): void {
  if (window.location.pathname === to) return;
  window.history.pushState({}, "", to);
  window.dispatchEvent(new Event("coral:navigate"));
}

export function useNavigate(): (to: string) => void {
  return useCallback((to: string) => navigate(to), []);
}

/**
 * match reads the parameters out of a path against a pattern such as
 * `/cities/:cityId/layers/:layerId`. It returns undefined when the path is not
 * that screen.
 */
export function match(
  pattern: string,
  path: string,
): Record<string, string> | undefined {
  const expected = pattern.split("/").filter(Boolean);
  const actual = path.split("/").filter(Boolean);
  if (expected.length !== actual.length) return undefined;

  const parameters: Record<string, string> = {};
  for (let index = 0; index < expected.length; index += 1) {
    const part = expected[index] as string;
    const value = actual[index] as string;
    if (part.startsWith(":")) {
      parameters[part.slice(1)] = decodeURIComponent(value);
    } else if (part !== value) {
      return undefined;
    }
  }
  return parameters;
}
