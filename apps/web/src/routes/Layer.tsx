import { client } from "@coral-city/client";

import { Empty, Failure, Loading, Refusal } from "../components/Shell";
import { StateBadge, TruthBadge } from "../components/Truth";
import { navigate } from "../router";
import { useAsked } from "../useAsync";

export function Layer({ layerId }: { layerId: string }) {
  const asked = useAsked(() => client.layer(layerId), [layerId]);

  if (asked.loading) return <Loading what="this layer" />;
  if (asked.refusal) return <Refusal refusal={asked.refusal} />;
  if (asked.error) return <Failure error={asked.error} />;
  if (!asked.value) return null;

  const { layer, versions } = asked.value;

  return (
    <div className="page">
      <header className="page-head">
        {layer.cityId ? (
          <p className="crumb">
            <a href={`/cities/${layer.cityId}`}
               onClick={(event) => { event.preventDefault(); navigate(`/cities/${layer.cityId}`); }}>
              back to the place
            </a>
          </p>
        ) : (
          <p className="crumb">
            <a href="/world" onClick={(event) => { event.preventDefault(); navigate("/world"); }}>
              back to the shared world
            </a>
          </p>
        )}
        <h1>{layer.title}</h1>
        <p>{layer.description}</p>
        <dl className="facts inline">
          <div><dt>Kind</dt><dd>{layer.kind.replace(/_/g, " ")}</dd></div>
          <div><dt>Scope</dt><dd>{layer.scopeKind === "city" ? "this place" : "the shared world"}</dd></div>
          <div><dt>Attributed to</dt><dd>{layer.attributedOrgId}</dd></div>
        </dl>
      </header>

      <section>
        <h2>Versions</h2>
        <p className="quiet">
          Newest first. A correction never rewrites what came before: it becomes
          a new version that supersedes it, and the earlier one stays exactly as
          it was recorded.
        </p>

        {versions.length === 0 ? (
          <Empty>This layer holds no version you may see.</Empty>
        ) : (
          <ol className="versions">
            {versions.map((version) => (
              <li key={version.id}>
                <a href={`/layers/${layer.id}/versions/${version.id}`}
                   onClick={(event) => {
                     event.preventDefault();
                     navigate(`/layers/${layer.id}/versions/${version.id}`);
                   }}>
                  <span className="ordinal">v{version.ordinal}</span>
                  <span className="badges">
                    <TruthBadge truthClass={version.truthClass} />
                    <StateBadge version={version} />
                  </span>
                  <span className="quiet mono">{version.contentDigest.slice(0, 16)}…</span>
                  <span className="quiet">
                    measured {new Date(version.observedFrom).toISOString().slice(0, 10)}
                  </span>
                </a>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
