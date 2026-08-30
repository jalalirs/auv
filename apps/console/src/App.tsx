import { useCallback, useEffect, useState } from "react";

import { api, Refused } from "./api/client.js";
import type { Organisation, Principal } from "./api/client.js";
import { Places } from "./screens/Places.js";
import { Vehicles } from "./screens/Vehicles.js";
import { Queues } from "./screens/Queues.js";
import { Dives } from "./screens/Dives.js";
import { Refusals } from "./screens/Refusals.js";
import { Overview } from "./screens/Overview.js";
import { Access } from "./screens/Access.js";

/**
 * The operator console for the control plane.
 *
 * It manages resources and governance: who exists, what the platform publishes,
 * what hardware there is, who may use any of it, and what has been run. It is
 * not the application people dive in — that is a different thing entirely, and
 * conflating the two is how an administration screen ends up pretending to be
 * a product.
 */

type Screen = "overview" | "places" | "vehicles" | "queues" | "dives" | "access" | "refusals";

const screens: { id: Screen; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "places", label: "Places" },
  { id: "vehicles", label: "Vehicles" },
  { id: "queues", label: "Queues" },
  { id: "dives", label: "Dives" },
  { id: "access", label: "People and access" },
  { id: "refusals", label: "Refusals" },
];

function screenFromPath(): Screen {
  const first = window.location.pathname.split("/").filter(Boolean)[0];
  const known = screens.find((screen) => screen.id === first);
  return known?.id ?? "overview";
}

export function App() {
  const [signedIn, setSignedIn] = useState<
    { principal: Principal; organisations: Organisation[] } | null | undefined
  >(undefined);
  const [screen, setScreen] = useState<Screen>(screenFromPath);

  const refresh = useCallback(() => {
    api.me()
      .then(setSignedIn)
      .catch((error: unknown) => {
        // 401 is not a failure here; it is the platform saying nobody is signed
        // in, which is exactly what the sign-in screen exists for.
        if (error instanceof Refused && error.status === 401) setSignedIn(null);
        else setSignedIn(null);
      });
  }, []);

  useEffect(refresh, [refresh]);

  useEffect(() => {
    const onPop = () => setScreen(screenFromPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const go = (next: Screen) => {
    window.history.pushState(null, "", `/${next}`);
    setScreen(next);
  };

  if (signedIn === undefined) {
    return <div className="signin"><p className="loading">Asking the platform who you are…</p></div>;
  }
  if (signedIn === null) return <SignIn onSignedIn={refresh} />;

  return (
    <div className="shell">
      <aside className="rail">
        <div className="mark">
          <h1>Coral City</h1>
          <p>control plane</p>
        </div>
        <nav>
          {screens.map((entry) => (
            <a
              key={entry.id}
              href={`/${entry.id}`}
              aria-current={screen === entry.id ? "page" : undefined}
              onClick={(event) => { event.preventDefault(); go(entry.id); }}
            >
              {entry.label}
            </a>
          ))}
        </nav>
        <div className="whoami">
          <strong>{signedIn.principal.displayName}</strong>
          <span>{signedIn.organisations.map((org) => org.name).join(", ") || "no institution"}</span>
          <p style={{ margin: "0.6rem 0 0" }}>
            <button
              className="quiet"
              onClick={() => { void api.signOut().finally(() => setSignedIn(null)); }}
            >
              Sign out
            </button>
          </p>
        </div>
      </aside>

      <main>
        {screen === "overview" && <Overview organisations={signedIn.organisations} />}
        {screen === "places" && <Places />}
        {screen === "vehicles" && <Vehicles />}
        {screen === "queues" && <Queues />}
        {screen === "dives" && <Dives organisations={signedIn.organisations} />}
        {screen === "access" && <Access />}
        {screen === "refusals" && <Refusals />}
      </main>
    </div>
  );
}

function SignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("");
  const [secret, setSecret] = useState("");
  const [refusal, setRefusal] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setRefusal(null);
    api.signIn(email, secret)
      .then(onSignedIn)
      .catch((error: unknown) => {
        // The platform refuses a wrong secret and an unknown address the same
        // way, and so does this: saying which was wrong would tell somebody
        // whether an address is registered here.
        setRefusal(
          error instanceof Refused && error.status === 401
            ? "That address and secret were not accepted."
            : "The platform could not be reached.",
        );
      })
      .finally(() => setBusy(false));
  };

  return (
    <div className="signin">
      <form onSubmit={submit}>
        <h1>Coral City</h1>
        <p className="lede">The control plane. Resources and governance.</p>

        <label htmlFor="email">Address</label>
        <input
          id="email" type="email" autoComplete="username" required
          value={email} onChange={(event) => setEmail(event.target.value)}
        />

        <label htmlFor="secret">Secret</label>
        <input
          id="secret" type="password" autoComplete="current-password" required
          value={secret} onChange={(event) => setSecret(event.target.value)}
        />

        {refusal && <p className="refused" style={{ marginBottom: "1rem" }}>{refusal}</p>}

        <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      </form>
    </div>
  );
}
