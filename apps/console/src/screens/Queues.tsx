import { useState } from "react";

import { api } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered, Tag, When } from "./parts.js";
import { Grants } from "./Access.js";

/** The hardware, and who may submit to it. */
export function Queues() {
  const [opened, setOpened] = useState<string | null>(null);
  const queues = useAsked(() => api.queues(), []);

  return (
    <>
      <h2>Queues</h2>
      <p className="lede">
        The governed resource is the queue, not the device: a queue holds
        however many devices it holds, so adding hardware is an insert rather
        than a change to the platform. Hardware carries no discoverability —
        somebody who cannot run on a queue has no reason to learn it exists.
      </p>

      <Answered
        asked={queues}
        empty={{
          of: (value) => value.queues.length === 0,
          say: "No queue is visible to you. Hardware is granted, never discovered, so a queue nobody has granted you is indistinguishable from one that does not exist.",
        }}
      >
        {(value) => (
          <div className="scroll">
            <table>
              <thead>
                <tr><th>Handle</th><th>Name</th><th>Free</th><th>Lease</th><th>State</th><th>Opened</th></tr>
              </thead>
              <tbody>
                {value.queues.map((queue) => (
                  <tr key={queue.id}>
                    <td className="mono">
                      <a href="#" onClick={(event) => {
                        event.preventDefault();
                        setOpened(opened === queue.id ? null : queue.id);
                      }}>{queue.slug}</a>
                    </td>
                    <td>{queue.name}</td>
                    <td className="num">
                      {queue.devices === 0
                        ? <span style={{ color: "var(--muted)" }}>no hardware</span>
                        : <>{queue.free} of {queue.devices}</>}
                    </td>
                    <td className="num">{Math.round(queue.leaseSeconds / 60)} min</td>
                    <td>
                      {queue.draining
                        ? <Tag kind="warn">draining</Tag>
                        : queue.free > 0
                          ? <Tag kind="good">accepting</Tag>
                          : <Tag kind="idle">full</Tag>}
                    </td>
                    <td><When value={queue.createdAt} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Answered>

      {opened && <QueueDetail key={opened} id={opened} />}
    </>
  );
}

function QueueDetail({ id }: { id: string }) {
  const devices = useAsked(() => api.devices(id), [id]);

  return (
    <>
      <h3>Devices</h3>
      <Answered
        asked={devices}
        empty={{
          of: (value) => value.devices.length === 0,
          say: "This queue holds no hardware. An agent registers what it found when it starts, so an empty queue usually means no agent has reported one yet.",
        }}
      >
        {(value) => (
          <div className="scroll">
            <table>
              <thead>
                <tr><th>Index</th><th>Model</th><th>Memory</th><th>UUID</th><th>Host</th><th>State</th></tr>
              </thead>
              <tbody>
                {value.devices.map((device) => (
                  <tr key={device.id}>
                    <td className="num">{device.deviceIndex}</td>
                    <td>{device.model || <span style={{ color: "var(--muted)" }}>—</span>}</td>
                    <td className="num">{(device.memoryBytes / 1024 ** 3).toFixed(0)} GiB</td>
                    <td className="mono">{device.uuid}</td>
                    <td className="mono">{device.targetId}</td>
                    <td>{device.enabled ? <Tag kind="good">enabled</Tag> : <Tag kind="bad">disabled</Tag>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Answered>

      <Grants
        assetId={id}
        noun="queue"
        grants={() => api.queueGrants(id)}
        grant={(kind, subject, role) => api.grantQueue(id, kind, subject, role)}
        revoke={(bindingId) => api.revokeQueueGrant(id, bindingId)}
      />
    </>
  );
}
