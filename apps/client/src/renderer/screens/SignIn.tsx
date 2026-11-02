// Signing in, with Google and nothing else.
//
// Signing in and signing up are the same button: the platform makes a person
// and their own space the first time it sees a Google account. Nobody signs in
// with a secret (those are for programs, not people), and the platform is fixed
// when the app is built rather than typed in.

import { useEffect, useState } from "react";

import { Platform, Refused } from "@coral-city/api";

import { Badge } from "./parts.js";

/**
 * Why nothing answered, when it can be told.
 *
 * In a browser, a page cannot call a platform on another origin that does not
 * invite it, and the browser reports the refusal to the page exactly as it
 * reports a machine that is switched off: a failed fetch, and nothing else. So
 * this said "Nothing answered — is the box awake?" about a box that was awake
 * and answering, which sends a person to check the wrong thing. The desktop
 * application is not a page on an origin and never meets this.
 */
/**
 * The platform an installed copy signs in to, fixed when it is built
 * (VITE_IOCEAN_PLATFORM, set by tools/release-mac); a copy run from source
 * looks for one on this machine unless .env.local names another.
 */
const PLATFORM = (import.meta.env.VITE_IOCEAN_PLATFORM as string | undefined) ?? "http://127.0.0.1:18080";

export function whyNothingAnswered(address: string, here: string | null): string {
  const unreached = `Nothing answered at ${address}. Is the box awake, and are you on its network?`;
  if (here === null || here.startsWith("file:")) return unreached;
  try {
    const there = new URL(address).origin;
    const ours = new URL(here).origin;
    if (there !== ours) {
      return `This page is at ${ours} and a browser will not let it call ${there}. ` +
        `Sign in to ${ours} instead — it forwards to the platform — or use the desktop application.`;
    }
  } catch {
    return unreached;
  }
  return unreached;
}

export function SignIn({ onSignedIn }: {
  onSignedIn: (platform: Platform) => void;
}): React.JSX.Element {
  const [trying, setTrying] = useState(false);
  const [refusal, setRefusal] = useState("");

  // Google happens in the system browser and comes back through
  // iocean://signed-in with a one-minute code, traded here for a session. Only
  // the desktop application can hear that link.
  const auth = typeof window === "undefined" ? undefined : window.coralCity?.auth;
  useEffect(() => {
    if (auth === undefined) return;
    return auth.onHandoff((code) => {
      void (async () => {
        setTrying(true);
        setRefusal("");
        try {
          onSignedIn(await Platform.exchange(PLATFORM, code));
        } catch (problem) {
          setRefusal(problem instanceof Refused
            ? "That sign-in had expired. Continue with Google again."
            : whyNothingAnswered(PLATFORM, typeof location === "undefined" ? null : location.href));
        } finally {
          setTrying(false);
        }
      })();
    });
  }, [auth, onSignedIn]);

  function google(): void {
    if (auth === undefined) return;
    setRefusal("");
    auth.openGoogle(Platform.googleSignIn(PLATFORM, "desktop"))
      .catch(() => setRefusal("The browser did not open. Try again."));
  }

  // Opened on the image of the thing itself: a vehicle over a reef, buoys in
  // the water, the ground surveyed under it. What the platform is, before a
  // word is read.
  return (
    <div className="middle boot">
      <Badge under="Dive a vehicle you brought, in water we keep" />
      <div className="panel">
        {auth !== undefined ? (
          <>
            <button type="button" className="google" onClick={google} disabled={trying}>
              {trying ? "Signing in…" : "Continue with Google"}
            </button>
            <p className="or">Your browser opens to sign in or sign up, and you come back here.</p>
          </>
        ) : (
          <p className="or">Sign in from the iOcean app.</p>
        )}
        <p className="refusal">{refusal}</p>
      </div>
    </div>
  );
}
