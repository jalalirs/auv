import { api } from "../api/client.js";
import type { Organisation } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered } from "./parts.js";

/**
 * What the platform holds, at a glance.
 *
 * Every number here is one the platform said. Where a count would need a
 * question this caller may not ask, it is absent rather than guessed.
 */
export function Overview({ organisations }: { organisations: Organisation[] }) {
  const build = useAsked(() => api.platform(), []);
  const cities = useAsked(() => api.cities(), []);
  const vehicles = useAsked(() => api.vehicles(), []);
  const queues = useAsked(() => api.queues(), []);

  const free = queues.state === "answered"
    ? queues.value.queues.reduce((sum, queue) => sum + queue.free, 0) : undefined;
  const devices = queues.state === "answered"
    ? queues.value.queues.reduce((sum, queue) => sum + queue.devices, 0) : undefined;

  return (
    <>
      <h2>Overview</h2>
      <p className="lede">
        What this installation holds, and what of it you may see. A place or a
        vehicle nobody has granted you does not appear here and is not counted.
      </p>

      <div className="cards">
        <div className="card">
          <div className="label">Places</div>
          <div className="value">{cities.state === "answered" ? cities.value.cities.length : "—"}</div>
          <div className="note">visible to you</div>
        </div>
        <div className="card">
          <div className="label">Vehicles</div>
          <div className="value">{vehicles.state === "answered" ? vehicles.value.vehicles.length : "—"}</div>
          <div className="note">visible to you</div>
        </div>
        <div className="card">
          <div className="label">Hardware</div>
          <div className="value">{free ?? "—"}<span style={{ fontSize: "1rem", color: "var(--muted)" }}> / {devices ?? "—"}</span></div>
          <div className="note">devices free</div>
        </div>
        <div className="card">
          <div className="label">Institutions</div>
          <div className="value">{organisations.length}</div>
          <div className="note">you belong to</div>
        </div>
      </div>

      <h3>This installation</h3>
      <Answered asked={build}>
        {(info) => (
          <div className="scroll">
            <table>
              <tbody>
                <tr><th style={{ width: "12rem" }}>Service</th><td>{info.name}</td></tr>
                <tr><th>Version</th><td className="mono">{info.version}</td></tr>
                <tr><th>Commit</th><td className="mono">{info.commit}</td></tr>
                <tr><th>Built</th><td className="mono">{info.builtAt}</td></tr>
              </tbody>
            </table>
          </div>
        )}
      </Answered>
    </>
  );
}
