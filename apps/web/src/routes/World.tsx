import { client } from "@coral-city/client";

import { Empty, Failure, Loading, Refusal } from "../components/Shell";
import { navigate } from "../router";
import { useAsked } from "../useAsync";

/**
 * The shared world: the layers that belong to the platform rather than to any
 * one place, and which every place inherits as background and as boundary
 * conditions.
 */
export function World() {
  const asked = useAsked(() => client.worldLayers(), []);

  if (asked.loading) return <Loading what="the shared world" />;
  if (asked.refusal) return <Refusal refusal={asked.refusal} />;
  if (asked.error) return <Failure error={asked.error} />;

  const layers = asked.value?.layers ?? [];

  return (
    <div className="page">
      <header className="page-head">
        <h1>The shared world</h1>
        <p className="quiet">
          Global layers, held by the platform itself. Every place inherits them
          as background and as the boundary conditions a local model solves
          within.
        </p>
      </header>

      {layers.length === 0 ? (
        <Empty>
          No global layer has been contributed yet. Worldwide bathymetry and a
          daily ocean forecast belong here; until they are ingested, nothing is
          shown in their place.
        </Empty>
      ) : (
        <ul className="rows">
          {layers.map((layer) => (
            <li key={layer.id}>
              <a href={`/layers/${layer.id}`}
                 onClick={(event) => { event.preventDefault(); navigate(`/layers/${layer.id}`); }}>
                <span className="kind">{layer.kind.replace(/_/g, " ")}</span>
                <strong>{layer.title}</strong>
                <span className="quiet">{layer.description}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
