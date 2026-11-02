// The organisation you are working in: which one, how much of its month is
// left, and, for an institution's administrator, who it approves.
//
// Everybody has a space of their own. An institution adds people by listing
// their addresses; whoever signs in with Google as one of them works here on
// the institution's quota.

import { useCallback, useEffect, useState } from "react";

import type { Approval, Platform, Quota } from "@coral-city/api";

import { rememberOrganisation, type Held } from "../platform/held.js";
import { Empty, Fact } from "./parts.js";
import { SkeletonLines } from "../ui/components.js";

/** Runs asked for since the first of this month, UTC: what the monthly limit counts. */
export function startedThisMonth(held: Held, now = new Date()): number {
  const since = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1);
  return held.runs.filter((r) => Date.parse(r.run.requestedAt) >= since).length;
}

export function Organisation({ platform, held, onSwitch }: {
  platform: Platform;
  held: Held;
  onSwitch: () => void;
}): React.JSX.Element | null {
  const here = held.institution;
  const [quota, setQuota] = useState<Quota | undefined>();
  useEffect(() => {
    if (here === undefined) return;
    let gone = false;
    void platform.quota(here.id).then((q) => { if (!gone) setQuota(q); }).catch(() => undefined);
    return () => { gone = true; };
  }, [platform, here]);

  if (here === undefined) return null;
  const started = startedThisMonth(held);
  const limit = quota?.maxDivesMonthly ?? null;

  return (
    <section>
      <h2>Working in</h2>
      <div className="facts">
        {held.organisations.length > 1 ? (
          <label className="switch">
            organisation
            <select value={here.id} onChange={(e) => { rememberOrganisation(e.target.value); onSwitch(); }}>
              {held.organisations.map((o) => (
                <option key={o.id} value={o.id}>{o.personalOf ? `${o.name} (your own)` : o.name}</option>
              ))}
            </select>
          </label>
        ) : (
          <Fact of="organisation" is={here.personalOf ? `${here.name} (your own)` : here.name} />
        )}
        <Fact of="dives this month"
              is={limit === null ? `${started}, no monthly limit` : `${started} of ${limit}`} />
      </div>
      {!here.personalOf && <Approvals platform={platform} organisation={here.id} onChange={onSwitch} />}
    </section>
  );
}

/**
 * Who the institution approves. Only its administrators may read the list, so
 * for everybody else this is not shown at all.
 */
function Approvals({ platform, organisation, onChange }: {
  platform: Platform;
  organisation: string;
  onChange: () => void;
}): React.JSX.Element | null {
  const [approvals, setApprovals] = useState<Approval[] | undefined>();
  const [allowed, setAllowed] = useState(true);
  const [adding, setAdding] = useState("");
  const [trouble, setTrouble] = useState("");

  const read = useCallback(() => {
    platform.approvals(organisation)
      .then((list) => { setApprovals(list); setAllowed(true); })
      .catch(() => setAllowed(false));
  }, [platform, organisation]);
  useEffect(read, [read]);

  if (!allowed) return null;
  const changed = (): void => { read(); onChange(); };
  const said = (problem: unknown): void => setTrouble(String((problem as Error)?.message ?? problem));

  return (
    <>
      <h2>People this organisation approves</h2>
      <p className="aside">
        Whoever signs in with Google as one of these addresses works here, on this
        organisation's quota. Taking an address off takes them out at once.
      </p>
      <form className="naming" onSubmit={(event) => {
        event.preventDefault();
        const email = adding.trim();
        if (!email) return;
        setTrouble("");
        void platform.approveEmail(organisation, email).then(() => { setAdding(""); changed(); }).catch(said);
      }}>
        <input value={adding} onChange={(e) => setAdding(e.target.value)} type="email"
               placeholder="name@institution.org" spellCheck={false} />
        <button type="submit" disabled={!adding.trim()}>Approve</button>
      </form>
      {trouble ? <p className="refusal">{trouble}</p> : null}
      {approvals === undefined ? <SkeletonLines lines={3} /> : approvals.length === 0 ? (
        <Empty title="Nobody yet">Approve an address and its owner joins when they next sign in.</Empty>
      ) : (
        <div className="ledger">
          {approvals.map((a) => (
            <div className="row" key={a.email || a.domain}>
              <strong>{a.email || `everyone at ${a.domain}`}</strong>
              <span className="when">{a.domain ? "a Workspace domain, given by iOcean" : "an address"}</span>
              {a.email ? (
                <button type="button" className="quiet"
                        onClick={() => { void platform.withdrawEmail(organisation, a.email!).then(changed).catch(said); }}>
                  Remove
                </button>
              ) : <span />}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
