import { client } from "@coral-city/client";

import { Empty, Failure, Loading, Refusal } from "../components/Shell";
import { useAsked } from "../useAsync";

/**
 * Why the caller has been refused.
 *
 * "Why can I not see this" is a first-class question with a row behind it, not
 * a log line somebody else has to go and read.
 */
export function Refusals() {
  const asked = useAsked(() => client.denials(), []);

  if (asked.loading) return <Loading what="your refusals" />;
  if (asked.refusal) return <Refusal refusal={asked.refusal} />;
  if (asked.error) return <Failure error={asked.error} />;

  const denials = asked.value?.denials ?? [];

  return (
    <div className="page">
      <header className="page-head">
        <h1>Refusals</h1>
        <p className="quiet">
          Every time the platform declined something you asked for, and why. A
          hidden refusal reported absence; a visible one said the thing exists
          and access may be requested.
        </p>
      </header>

      {denials.length === 0 ? (
        <Empty>Nothing you have asked for has been refused.</Empty>
      ) : (
        <table className="denials">
          <thead>
            <tr><th>When</th><th>Asked to</th><th>On</th><th>Answer</th><th>Reason</th></tr>
          </thead>
          <tbody>
            {denials.map((denial) => (
              <tr key={denial.id}>
                <td className="quiet">
                  {new Date(denial.occurredAt).toISOString().replace("T", " ").slice(0, 19)}
                </td>
                <td className="mono">{denial.action}</td>
                <td className="quiet">{denial.resourceKind}</td>
                <td>
                  <span className={`effect effect-${denial.effect}`}>
                    {denial.effect === "hidden" ? "reported as absent" : "refused openly"}
                  </span>
                </td>
                <td>{denial.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
