import type { ReactNode } from "react";

import type { Asked } from "../useAsync.js";

/**
 * What a screen shows while it is asking, when it was refused, and when there
 * is nothing to show.
 *
 * A refusal is kept rather than flattened into an error, because it is often
 * the most informative answer a screen can give: a hidden refusal reports
 * absence, and a visible one says the thing exists and may be asked for.
 */
export function Answered<T>({
  asked, empty, children,
}: {
  asked: Asked<T>;
  empty?: { of: (value: T) => boolean; say: string };
  children: (value: T) => ReactNode;
}) {
  if (asked.state === "asking") return <p className="loading">Asking the platform…</p>;

  if (asked.state === "refused") {
    return (
      <div className="refused">
        <strong>{asked.refusal.problem?.message ?? "The platform refused this."}</strong>
        {asked.refusal.mayBeRequested
          ? "This exists and access to it may be requested."
          : "Either it does not exist, or it is not yours to know about. The platform does not distinguish the two."}
      </div>
    );
  }

  if (asked.state === "broken") {
    return <div className="refused"><strong>The platform could not be reached.</strong>{asked.error.message}</div>;
  }

  if (empty && empty.of(asked.value)) return <div className="empty">{empty.say}</div>;
  return <>{children(asked.value)}</>;
}

export function Tag({ kind, children }: { kind: "good" | "warn" | "bad" | "idle" | "accent"; children: ReactNode }) {
  return <span className={`tag tag-${kind}`}>{children}</span>;
}

/** A digest is long and only its first characters are ever compared by eye. */
export function Digest({ value }: { value: string | undefined }) {
  if (!value) return <span style={{ color: "var(--muted)" }}>—</span>;
  return <code title={value}>{value.slice(0, 12)}…</code>;
}

export function When({ value }: { value: string | undefined | null }) {
  if (!value) return <span style={{ color: "var(--muted)" }}>—</span>;
  const at = new Date(value);
  return <span title={at.toISOString()}>{at.toLocaleString()}</span>;
}
