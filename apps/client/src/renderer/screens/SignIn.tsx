// Signing in, with Google and nothing else.
//
// Signing in and signing up are the same button: the platform makes a person
// and their own space the first time it sees a Google account. Nobody signs in
// with a secret (those are for programs, not people), and the platform is fixed
// when the app is built rather than typed in.

import { useEffect, useState } from "react";

import { Platform, Refused } from "@coral-city/api";

import boot from "../../../assets/boot.jpg";

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
  // word is read. The picture carries the name, so the panel only signs in.
  return (
    <div className="middle boot sign-in">
      <img className="boot-art" src={boot} alt="" />
      <div className="panel">
        <h1>Sign in to iOcean</h1>
        <p className="lead">Dive a vehicle you brought, in water we keep.</p>
        {auth !== undefined ? (
          <>
            <button type="button" className="google" onClick={google} disabled={trying}>
              <GoogleMark />
              <span>{trying ? "Signing in…" : "Continue with Google"}</span>
            </button>
            <p className="or">Your browser opens to sign in, or to make an account if you have none, and brings you back here.</p>
          </>
        ) : (
          <p className="or">Sign in from the iOcean app.</p>
        )}
        <p className="refusal">{refusal}</p>
      </div>
    </div>
  );
}

/** Google's own four-colour G, as its sign-in button guidelines draw it. */
function GoogleMark(): React.JSX.Element {
  return (
    <svg className="mark" viewBox="0 0 48 48" width="18" height="18" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
    </svg>
  );
}
