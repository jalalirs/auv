// Who you are here, and what you have been given.

import { useEffect, useState } from "react";

import type { Device, Platform } from "@coral-city/api";

import type { Held } from "./Deck.js";
import { Empty, Fact, PageHead, Pill } from "./parts.js";

const LIVE = new Set(["queued", "preparing", "running"]);

export function Profile({ platform, held, free, devices }: {
  platform: Platform;
  held: Held;
  free: number;
  devices: number;
}): React.JSX.Element {
  // The cards behind each queue, asked for once the page is open. What the
  // box is doing is its own business to report, and this is the one page
  // that reports it back.
  const [cards, setCards] = useState<Map<string, Device[]>>(new Map());
  useEffect(() => {
    let gone = false;
    void Promise.all(held.queues.map(async (q) => [q.id, await platform.devices(q.id).catch((): Device[] => [])] as const))
      .then((each) => { if (!gone) setCards(new Map(each)); });
    return () => { gone = true; };
  }, [platform, held.queues]);
  const inFlight = held.runs.filter((r) => LIVE.has(r.run.state));

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
        <h2>The machines</h2>
        {held.queues.every((q) => (cards.get(q.id) ?? []).length === 0) ? (
          <Empty title="No cards reported yet">
            A host places its cards in a queue when its agent starts.
          </Empty>
        ) : (
          <div className="ledger">
            {held.queues.flatMap((queue) => (cards.get(queue.id) ?? []).map((card) => {
              const holding = inFlight.filter((r) => r.run.placement?.holds.some((h) => h.deviceId === card.id));
              const held_ = holding.reduce((n, r) => n + (r.run.placement?.holds
                .filter((h) => h.deviceId === card.id).reduce((m, h) => m + h.gpuMemoryBytes, 0) ?? 0), 0);
              return (
                <div className="row" key={card.id}>
                  <strong>card {card.deviceIndex}</strong>
                  <span className="when">{card.model} · {(card.memoryBytes / 2 ** 30).toFixed(0)} GiB</span>
                  <Pill kind={holding.length === 0 ? "good" : "busy"}>
                    {holding.length === 0 ? "free" : `${holding.length} dive${holding.length > 1 ? "s" : ""} · ${(held_ / 2 ** 30).toFixed(0)} GiB held`}
                  </Pill>
                </div>
              );
            }))}
          </div>
        )}
        <p className="aside">{inFlight.length === 0 ? "Nothing in flight." : `${inFlight.length} in flight: ${inFlight.map((r) => r.run.state).join(", ")}.`}</p>
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
