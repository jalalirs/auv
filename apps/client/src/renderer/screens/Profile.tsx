// Who you are here, and what you have been given.

import type { Platform } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { Empty, Fact, PageHead, Pill } from "./parts.js";

export function Profile({ platform, held, free, devices }: {
  platform: Platform;
  held: Held;
  free: number;
  devices: number;
}): React.JSX.Element {
  return (
    <>
      <PageHead title={held.you.displayName || "You"}
        says="What you are able to do here is what somebody granted you. Nothing on this page is a setting; it is a description." />

      <section>
        <div className="hero">
          <div className="said">
            <div className="eyebrow">Signed in</div>
            <h2>{held.you.email ?? held.you.displayName}</h2>
            <p>{held.institution?.name ?? "You are not a member of any institution."}</p>
            <div className="facts">
              <Fact of="platform" is={platform.address.replace(/^https?:\/\//, "")} />
              <Fact of="queues" is={String(held.queues.length)} />
              <Fact of="machines" is={`${free} free of ${devices}`} />
            </div>
          </div>
        </div>
      </section>

      <section>
        <h2>Queues you may run on</h2>
        {held.queues.length === 0 ? (
          <Empty title="None granted">
            A queue holds machines, and access is granted to the queue rather than
            to a machine — which is what lets one workstation and a rack be
            described the same way.
          </Empty>
        ) : (
          <div className="ledger">
            {held.queues.map((queue) => (
              <div className="row" key={queue.id}>
                <strong>{queue.name}</strong>
                <span className="when">
                  {queue.runtimes?.[0] ?? "has not said what it runs"}
                </span>
                <Pill kind={queue.free > 0 ? "good" : "bad"}>
                  {queue.free} free of {queue.devices}
                </Pill>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>Coming</h2>
        <Empty title="Your people, and what they may do" soon="in the console, not here">
          Granting access, adding members and reading refusals live in the control
          plane's console. They belong to whoever runs the platform rather than to
          whoever dives in it, which is why they are not in this application.
        </Empty>
      </section>
    </>
  );
}
