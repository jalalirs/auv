// What flies the vehicle, other than you — and what each one has done.
//
// The controllers this institution has deployed, newest first: each an image
// pinned by digest, with what it needs of a machine, and every build it has
// had folded under one row — a dive pins a build, a person thinks in
// controllers. A stack is what a dive
// is defined with on the dive page; deploying one is the SDK's job, from a
// terminal, because a build is a build.
//
// And beside each, what it flew. The page used to answer "what have I
// uploaded", which is the smallest question anybody has about a controller.
// The one they have is which of these should fly my mission, and the answer
// was already in the record: every dive the institution defined, which stack
// flew it, and what became of it. A controller that has never flown says so
// in those words — it is the most useful row here, because it is the
// difference between a controller somebody deployed and one somebody trusts.

import { ControllerArt } from "../parts/ControllerArt.js";
import type { Held } from "./Deck.js";
import { headToHead, recordOf, saidAs } from "./flown.js";
import { Empty, PageHead, Pill, ago } from "./parts.js";

export function Autonomy({ held }: { held: Held }): React.JSX.Element {
  return (
    <>
      <PageHead title="Autonomy"
        says="Your controllers, in containers, pinned by digest. Each talks ROS 2 to the vehicle exactly as it would to a real one and imports nothing of ours — the same binary should run in a tank and in the sea." />

      <section>
        <h2>Deployed to {held.institution?.name ?? "your institution"}</h2>
        {held.controllers.length === 0 ? (
          <Empty title="Nothing deployed yet">
            Write a controller against the SDK and deploy it with <code>iocean deploy</code>; it appears here and on the dive page.
          </Empty>
        ) : (
          <div className="ledger">
            {held.controllers.map(({ slug, name, newest, builds }) => {
              const needs = (newest.needs ?? {}) as { gpu?: boolean; gpuMemoryBytes?: number; cpu?: number; memoryBytes?: number };
              const card = needs.gpu || newest.wantsGpu
                ? `${needs.gpuMemoryBytes ? (needs.gpuMemoryBytes / 2 ** 30).toFixed(0) + " GiB of a card" : "a card"}`
                : "no card";
              const flew = recordOf(name, held.runs);
              // And against the others, where the dives were the same dives.
              // The average above is over whatever this one happened to fly, so
              // it cannot say which controller is better; this can, and only
              // where the bench flew both over the same task, suite, hull and
              // reef.
              const against = headToHead(name, held.controllers.map((one) => one.name), held.runs);
              return (
                <div className="row" key={slug}>
                  <ControllerArt digest={newest.imageDigest} size={28} />
                  <strong>{name}</strong>
                  <span className="when">
                    {slug} · {newest.imageDigest.slice(7, 19)} · {ago(newest.createdAt)}
                    {builds.length > 1 ? ` · ${builds.length} builds` : ""}
                    <br />
                    {flew.dives === 0
                      ? "never flown"
                      : [
                          `${flew.dives} ${flew.dives === 1 ? "dive" : "dives"}`,
                          flew.score === undefined ? undefined : `${(flew.score * 100).toFixed(0)}% scored`,
                          flew.driftM === undefined ? undefined : `${flew.driftM.toFixed(1)} m drift`,
                          flew.energyWh === undefined ? undefined : `${flew.energyWh.toFixed(1)} Wh`,
                          flew.struck > 0 ? `${flew.struck} struck` : undefined,
                          flew.lastAt === undefined ? undefined : `last ${ago(flew.lastAt)}`,
                        ].filter(Boolean).join(" · ")}
                    {flew.neverFlew > 0
                      ? ` · ${flew.neverFlew} never flew (the platform could not start them)`
                      : ""}
                    {against.length === 0 ? null : (
                      <>
                        <br />
                        {against.map((one) => saidAs(one)).join(" · ")}
                      </>
                    )}
                  </span>
                  <Pill kind={needs.gpu || newest.wantsGpu ? "busy" : undefined}>{card}</Pill>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <h2>Deploying one</h2>
        <Empty title="From the SDK" soon="one command">
          <code>pip install -e packages/sdk-python</code>, write a class against <code>iocean.Controller</code>,
          try it in the tank with <code>iocean tank</code>, then <code>iocean deploy your.py --slug name</code>.
          A controller that is a model says what it needs with <code>--gpu-memory 8G</code>, and the scheduler places the dive where both it and the simulator fit.
        </Empty>
      </section>
    </>
  );
}
