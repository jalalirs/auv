import { useState } from "react";

import { api } from "../api/client.js";
import type { Organisation, Run } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered, Digest, Tag, When } from "./parts.js";

function stateTag(state: Run["state"]) {
  switch (state) {
    case "succeeded": return <Tag kind="good">succeeded</Tag>;
    case "running": return <Tag kind="good">running</Tag>;
    case "preparing": return <Tag kind="warn">preparing</Tag>;
    case "queued": return <Tag kind="idle">queued</Tag>;
    case "failed": return <Tag kind="bad">failed</Tag>;
    case "cancelled": return <Tag kind="idle">cancelled</Tag>;
    case "expired": return <Tag kind="bad">expired</Tag>;
    default: return <Tag kind="idle">{state}</Tag>;
  }
}

/** What an institution has composed, and what its runs did. */
export function Dives({ organisations }: { organisations: Organisation[] }) {
  const [orgId, setOrgId] = useState(organisations[0]?.id ?? "");
  const [opened, setOpened] = useState<string | null>(null);

  const dives = useAsked(() => api.dives(orgId), [orgId]);
  const autonomy = useAsked(() => api.autonomy(orgId), [orgId]);

  if (organisations.length === 0) {
    return (
      <>
        <h2>Dives</h2>
        <div className="empty">You do not belong to an institution, and a dive belongs to one.</div>
      </>
    );
  }

  return (
    <>
      <h2>Dives</h2>
      <p className="lede">
        A dive is a vehicle in a place, under conditions, flown by autonomy. It
        names package versions rather than assets, so publishing a newer vehicle
        does not silently turn an experiment into a different one.
      </p>

      {organisations.length > 1 && (
        <p style={{ marginBottom: "1.2rem" }}>
          <label htmlFor="org">Institution</label>
          <select
            id="org" value={orgId} onChange={(event) => setOrgId(event.target.value)}
            style={{ padding: "0.4rem", font: "inherit" }}
          >
            {organisations.map((org) => <option key={org.id} value={org.id}>{org.name}</option>)}
          </select>
        </p>
      )}

      <Answered
        asked={dives}
        empty={{
          of: (value) => value.dives.length === 0,
          say: "This institution has composed no dives. A dive needs a published place, a published vehicle, and conditions before it can be defined.",
        }}
      >
        {(value) => (
          <div className="scroll">
            <table>
              <thead><tr><th>Name</th><th>Place</th><th>Vehicle</th><th>Autonomy</th><th>Defined</th></tr></thead>
              <tbody>
                {value.dives.map((plan) => (
                  <tr key={plan.id}>
                    <td>
                      <a href="#" onClick={(event) => {
                        event.preventDefault();
                        setOpened(opened === plan.id ? null : plan.id);
                      }}>{plan.name}</a>
                    </td>
                    <td className="mono">{plan.cityVersionId.slice(0, 12)}…</td>
                    <td className="mono">{plan.vehicleVersionId.slice(0, 12)}…</td>
                    <td>
                      {plan.autonomyStackId
                        ? <Tag kind="accent">brought</Tag>
                        : <span style={{ color: "var(--muted)" }}>none</span>}
                    </td>
                    <td><When value={plan.createdAt} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Answered>

      {opened && <RunsOf key={opened} diveId={opened} />}

      <h3>Autonomy this institution has registered</h3>
      <Answered
        asked={autonomy}
        empty={{
          of: (value) => value.autonomy.length === 0,
          say: "No autonomy has been registered. A stack is a container image pinned by digest, never by tag, so that re-running a dive re-runs the same program.",
        }}
      >
        {(value) => (
          <div className="scroll">
            <table>
              <thead><tr><th>Handle</th><th>Name</th><th>Image</th><th>Digest</th><th>GPU</th></tr></thead>
              <tbody>
                {value.autonomy.map((stack) => (
                  <tr key={stack.id}>
                    <td className="mono">{stack.slug}</td>
                    <td>{stack.name}</td>
                    <td className="mono">{stack.imageRepository}</td>
                    <td><Digest value={stack.imageDigest.replace("sha256:", "")} /></td>
                    <td>{stack.wantsGpu ? <Tag kind="warn">shares one</Tag> : <Tag kind="idle">none</Tag>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Answered>
    </>
  );
}

function RunsOf({ diveId }: { diveId: string }) {
  const runs = useAsked(() => api.runs(diveId), [diveId]);

  return (
    <>
      <h3>Runs</h3>
      <p className="lede" style={{ marginBottom: "0.8rem" }}>
        A run copies every determinant when it is admitted — the digests, the
        seed, the runtime — so that editing the dive afterwards cannot change
        what a recorded result means. The same seed and the same digests is the
        same run.
      </p>
      <Answered
        asked={runs}
        empty={{
          of: (value) => value.runs.length === 0,
          say: "This dive has never been run.",
        }}
      >
        {(value) => (
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>State</th><th>Mode</th><th>Seed</th><th>Runtime</th>
                  <th>Place</th><th>Vehicle</th><th>Requested</th>
                </tr>
              </thead>
              <tbody>
                {value.runs.map((run) => (
                  <tr key={run.id}>
                    <td>{stateTag(run.state)}</td>
                    <td>{run.mode === "interactive" ? <Tag kind="accent">interactive</Tag> : <Tag kind="idle">batch</Tag>}</td>
                    <td className="mono num">{run.seed}</td>
                    <td className="mono">{run.runtimeVersion}</td>
                    <td><Digest value={run.cityDigest} /></td>
                    <td><Digest value={run.vehicleDigest} /></td>
                    <td><When value={run.requestedAt} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Answered>
    </>
  );
}
