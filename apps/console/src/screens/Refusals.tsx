import { api } from "../api/client.js";
import { useAsked } from "../useAsync.js";
import { Answered, Tag, When } from "./parts.js";

/**
 * What the platform has refused you, and why.
 *
 * A refusal is recorded rather than merely returned, so that somebody who
 * cannot do a thing can find out what authority it would have needed instead of
 * guessing.
 */
export function Refusals() {
  const denials = useAsked(() => api.denials(), []);

  return (
    <>
      <h2>Refusals</h2>
      <p className="lede">
        Every refusal you have received. A visible refusal says the thing exists
        and access may be requested; a hidden one says only that nothing is
        there, because saying more would itself disclose something.
      </p>

      <Answered
        asked={denials}
        empty={{
          of: (value) => value.denials.length === 0,
          say: "The platform has refused you nothing.",
        }}
      >
        {(value) => (
          <div className="scroll">
            <table>
              <thead><tr><th>Action</th><th>On</th><th>Effect</th><th>Reason</th><th>When</th></tr></thead>
              <tbody>
                {value.denials.map((denial) => (
                  <tr key={denial.id}>
                    <td className="mono">{denial.action}</td>
                    <td className="mono">{denial.resourceKind}</td>
                    <td>
                      {denial.effect === "visible"
                        ? <Tag kind="warn">may be requested</Tag>
                        : <Tag kind="idle">reported absent</Tag>}
                    </td>
                    <td>{denial.reason}</td>
                    <td><When value={denial.occurredAt} /></td>
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
