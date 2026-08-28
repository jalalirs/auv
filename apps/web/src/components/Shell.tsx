import type { ReactNode } from "react";
import { Refused } from "@coral-city/client";

import { navigate, usePath } from "../router";
import { useSession } from "../session";

const areas = [
  { path: "/", label: "Places" },
  { path: "/world", label: "Shared world" },
  { path: "/work", label: "Work" },
  { path: "/refusals", label: "Refusals" },
];

export function Shell({ children }: { children: ReactNode }) {
  const path = usePath();
  const { session, signOut } = useSession();

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="/" onClick={(event) => { event.preventDefault(); navigate("/"); }}>
          <span className="brand-mark" aria-hidden="true">CC</span>
          <span>
            <strong>Coral City</strong>
            <small>a hub for oceanic engineering and science</small>
          </span>
        </a>

        <nav aria-label="Areas">
          {areas.map((area) => (
            <a key={area.path}
               href={area.path}
               aria-current={path === area.path ? "page" : undefined}
               onClick={(event) => { event.preventDefault(); navigate(area.path); }}>
              {area.label}
            </a>
          ))}
        </nav>

        {session ? (
          <div className="who">
            <span>
              <strong>{session.principal.displayName}</strong>
              <small>
                {session.organisations.map((org) => org.name).join(", ") || "no institution"}
              </small>
            </span>
            <button type="button" onClick={() => void signOut()}>Sign out</button>
          </div>
        ) : null}
      </header>

      <main>{children}</main>
    </div>
  );
}

/** Loading says the platform has been asked and has not yet answered. */
export function Loading({ what }: { what: string }) {
  return <p className="quiet">Reading {what}…</p>;
}

/**
 * Refusal presents the platform's answer in its own terms.
 *
 * A hidden refusal reports absence, because the existence of some places is
 * itself sensitive. A visible one says the thing exists and access may be
 * requested. Flattening the two into "error" would discard the distinction the
 * platform went to some trouble to draw.
 */
export function Refusal({ refusal }: { refusal: Refused }) {
  if (refusal.notFound) {
    return (
      <section className="refusal">
        <h2>Nothing here</h2>
        <p>
          There is nothing at this address that you are entitled to see. It may
          not exist, or it may not be yours to know about — the platform does not
          distinguish the two, deliberately.
        </p>
      </section>
    );
  }
  return (
    <section className="refusal">
      <h2>Not yours to do</h2>
      <p>{refusal.message}</p>
      {refusal.accessMayBeRequested ? (
        <p className="quiet">
          This exists and access can be requested from whoever stewards it.
        </p>
      ) : null}
      <p className="quiet">Request {refusal.requestId}</p>
    </section>
  );
}

export function Failure({ error }: { error: Error }) {
  return (
    <section className="refusal">
      <h2>Something went wrong</h2>
      <p>{error.message}</p>
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}
