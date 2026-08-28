import { useEffect, useRef, useState } from "react";
import { client, type JobEvent, type Job } from "@coral-city/client";

import { Empty, Failure, Loading, Refusal } from "../components/Shell";
import { navigate } from "../router";
import { useSession } from "../session";
import { useAsked } from "../useAsync";

const terminal = new Set(["succeeded", "failed", "cancelled", "evicted", "timed_out"]);

export function Work() {
  const { session } = useSession();
  const orgId = session?.organisations[0]?.id ?? "";
  const jobs = useAsked(() => (orgId ? client.jobs(orgId) : Promise.resolve({ jobs: [] })), [orgId]);
  const quota = useAsked(
    () => (orgId ? client.quota(orgId) : Promise.resolve(undefined)),
    [orgId],
  );

  if (!orgId) {
    return (
      <div className="page">
        <h1>Work</h1>
        <Empty>You do not belong to an institution, so there is no work to show.</Empty>
      </div>
    );
  }
  if (jobs.loading) return <Loading what="this institution's work" />;
  if (jobs.refusal) return <Refusal refusal={jobs.refusal} />;
  if (jobs.error) return <Failure error={jobs.error} />;

  const capacity = quota.value;

  return (
    <div className="page">
      <header className="page-head">
        <h1>Work</h1>
        <p className="quiet">
          Finite containerised executions. Whether there is room is decided when
          work is submitted, and the platform records either answer.
        </p>
        {capacity ? (
          <dl className="facts inline">
            <div>
              <dt>In flight</dt>
              <dd>{capacity.inUse["jobs"] ?? 0} of {capacity.quota.maxConcurrentJobs}</dd>
            </div>
            <div>
              <dt>Processors</dt>
              <dd>{capacity.inUse["cpu"] ?? 0} of {capacity.quota.maxCpu}</dd>
            </div>
            <div>
              <dt>Memory</dt>
              <dd>
                {gigabytes(Number(capacity.inUse["memoryBytes"] ?? 0))} of{" "}
                {gigabytes(capacity.quota.maxMemoryBytes)}
              </dd>
            </div>
          </dl>
        ) : null}
      </header>

      {(jobs.value?.jobs ?? []).length === 0 ? (
        <Empty>This institution has submitted no work.</Empty>
      ) : (
        <ul className="rows">
          {(jobs.value?.jobs ?? []).map((job) => (
            <li key={job.id}>
              <a href={`/work/${job.id}`}
                 onClick={(event) => { event.preventDefault(); navigate(`/work/${job.id}`); }}>
                <span className={`state state-${job.state}`}>{job.state.replace("_", " ")}</span>
                <strong>{job.recipeId}</strong>
                <span className="quiet">
                  {new Date(job.createdAt).toISOString().replace("T", " ").slice(0, 19)} UTC
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const gigabytes = (bytes: number) => `${(bytes / 1024 ** 3).toFixed(1)} GiB`;

export function WorkDetail({ jobId }: { jobId: string }) {
  const asked = useAsked(() => client.job(jobId), [jobId]);
  const events = useJobEvents(jobId);

  if (asked.loading) return <Loading what="this work" />;
  if (asked.refusal) return <Refusal refusal={asked.refusal} />;
  if (asked.error) return <Failure error={asked.error} />;
  if (!asked.value) return null;

  const { job, attempts, outputs } = asked.value;

  return (
    <div className="page">
      <header className="page-head">
        <p className="crumb">
          <a href="/work" onClick={(event) => { event.preventDefault(); navigate("/work"); }}>
            Work
          </a>
        </p>
        <h1>{job.recipeId}</h1>
        <p className="badges">
          <span className={`state state-${job.state}`}>{job.state.replace("_", " ")}</span>
          {job.failureClass !== "none" ? (
            <span className="failure">{job.failureClass.replace(/_/g, " ")}</span>
          ) : null}
        </p>
        <dl className="facts inline">
          <div><dt>Image</dt><dd className="mono break">{job.imageDigest}</dd></div>
          <div><dt>Requested</dt><dd>{job.requestCpu} cpu · {gigabytes(job.requestMemoryBytes)}</dd></div>
          <div><dt>Deadline</dt><dd>{job.walltimeSeconds} s</dd></div>
        </dl>
      </header>

      <section>
        <h2>Attempts</h2>
        <p className="quiet">
          A retry creates an attempt, never a new job, so what produced a result
          stays a single thing however many times it had to be tried.
        </p>
        <table className="attempts">
          <thead>
            <tr><th>#</th><th>State</th><th>Worker</th><th>Started</th><th>Finished</th><th>Why it ended</th></tr>
          </thead>
          <tbody>
            {attempts.map((attempt) => (
              <tr key={attempt.id}>
                <td>{attempt.ordinal}</td>
                <td><span className={`state state-${attempt.state}`}>{attempt.state}</span></td>
                <td className="mono">{attempt.workerId.slice(0, 14)}…</td>
                <td className="quiet">{when(attempt.startedAt)}</td>
                <td className="quiet">{when(attempt.finishedAt)}</td>
                <td className="quiet">
                  {attempt.failureClass === "none" ? "—" : attempt.failureClass.replace(/_/g, " ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>What it produced</h2>
        {Object.keys(outputs).length === 0 ? (
          <Empty>Nothing was recorded.</Empty>
        ) : (
          <ul className="rows plain">
            {Object.entries(outputs).map(([name, objectId]) => (
              <li key={name}>
                <strong>{name}</strong> <span className="quiet mono">{objectId}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2>What happened</h2>
        <p className="quiet">
          The durable, ordered account of this work. It is what forensics reads,
          and it is never rewritten.
        </p>
        <ol className="events">
          {events.map((event) => (
            <li key={event.id}>
              <span className="sequence">{event.sequence}</span>
              <span className={`event event-${event.kind}`}>{event.kind.replace(/_/g, " ")}</span>
              <span className="quiet">{when(event.occurredAt)}</span>
              {Object.keys(event.detail).length > 0 ? (
                <pre>{JSON.stringify(event.detail, null, 2)}</pre>
              ) : null}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

const when = (value: string | undefined) =>
  value ? new Date(value).toISOString().replace("T", " ").slice(11, 19) : "—";

/**
 * useJobEvents follows a job's account of itself.
 *
 * It resumes from the last sequence number it saw, so nothing is missed and
 * nothing arrives twice, and it stops asking once the work has ended.
 */
function useJobEvents(jobId: string): JobEvent[] {
  const [events, setEvents] = useState<JobEvent[]>([]);
  const after = useRef(0);

  useEffect(() => {
    setEvents([]);
    after.current = 0;

    let running = true;
    const controller = new AbortController();

    const follow = async () => {
      while (running) {
        try {
          const answer = await client.jobEvents(jobId, after.current, controller.signal);
          if (!running) return;
          if (answer.events.length > 0) {
            after.current = answer.events[answer.events.length - 1]?.sequence ?? after.current;
            setEvents((existing) => [...existing, ...answer.events]);
            if (answer.events.some((event) => terminal.has(event.kind))) return;
          }
        } catch {
          // The account of the work is not going anywhere; a failed read is
          // retried on the next turn rather than reported as a fault.
          if (!running) return;
        }
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
    };

    void follow();
    return () => {
      running = false;
      controller.abort();
    };
  }, [jobId]);

  return events;
}

/** Terminal event kinds double as terminal job states. */
export type { Job };
