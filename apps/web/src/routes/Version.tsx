import { useState } from "react";
import { client, type ManifestFile } from "@coral-city/client";

import { Failure, Loading, Refusal } from "../components/Shell";
import { StateBadge, TruthBadge, describeUncertainty } from "../components/Truth";
import { navigate } from "../router";
import { useAsked } from "../useAsync";

/**
 * One piece of evidence, and everything needed to judge it.
 *
 * The rail on the right is the point of this screen: a value shown without its
 * coordinate reference, vertical datum, time basis, uncertainty, rights, and
 * provenance is not evidence, whatever it looks like.
 */
export function Version({ layerId, versionId }: { layerId: string; versionId: string }) {
  const asked = useAsked(() => client.version(layerId, versionId), [layerId, versionId]);
  const lineage = useAsked(() => client.lineage(layerId, versionId), [layerId, versionId]);

  if (asked.loading) return <Loading what="this evidence" />;
  if (asked.refusal) return <Refusal refusal={asked.refusal} />;
  if (asked.error) return <Failure error={asked.error} />;
  if (!asked.value) return null;

  const { version, uncertainty } = asked.value;
  const measuredOver =
    version.observedFrom === version.observedTo
      ? new Date(version.observedFrom).toISOString().replace("T", " ").slice(0, 19)
      : `${new Date(version.observedFrom).toISOString().replace("T", " ").slice(0, 19)} to ${new Date(
          version.observedTo,
        ).toISOString().replace("T", " ").slice(0, 19)} UTC`;

  return (
    <div className="page evidence-page">
      <div>
        <header className="page-head">
          <p className="crumb">
            <a href={`/layers/${layerId}`}
               onClick={(event) => { event.preventDefault(); navigate(`/layers/${layerId}`); }}>
              back to the layer
            </a>
          </p>
          <h1>Version {version.ordinal}</h1>
          <p className="badges">
            <TruthBadge truthClass={version.truthClass} />
            <StateBadge version={version} />
          </p>
          {version.state === "retracted" ? (
            <p className="withdrawn">
              Withdrawn: {version.retractionReason}. It is not deleted, and
              neither is its lineage — a retraction is a statement about a
              version, not its erasure.
            </p>
          ) : null}
          {version.supersededById ? (
            <p className="quiet">
              A later version supersedes this one.{" "}
              <a href={`/layers/${layerId}/versions/${version.supersededById}`}
                 onClick={(event) => {
                   event.preventDefault();
                   navigate(`/layers/${layerId}/versions/${version.supersededById}`);
                 }}>
                Read it
              </a>
              .
            </p>
          ) : null}
        </header>

        <section>
          <h2>What it contains</h2>
          <p className="quiet">
            The version's identity is the digest over this whole manifest, so two
            versions with the same digest hold exactly the same bytes under
            exactly the same names.
          </p>
          <table className="manifest">
            <thead>
              <tr><th>Path</th><th>Digest</th><th>Size</th><th>Type</th><th /></tr>
            </thead>
            <tbody>
              {(version.manifest ?? []).map((file) => (
                <ManifestRow key={file.relativePath} layerId={layerId}
                             versionId={versionId} file={file} />
              ))}
            </tbody>
          </table>
        </section>

        <section>
          <h2>What it came from</h2>
          {lineage.loading ? <Loading what="the lineage" /> : null}
          {lineage.value && lineage.value.derivedFrom.length === 0 ? (
            <p className="quiet">
              Nothing: this version was recorded directly rather than computed
              from other evidence.
            </p>
          ) : null}
          <ul className="rows">
            {(lineage.value?.derivedFrom ?? []).map((input) => (
              <li key={input.id}>
                <a href={`/layers/${input.layerId}/versions/${input.id}`}
                   onClick={(event) => {
                     event.preventDefault();
                     navigate(`/layers/${input.layerId}/versions/${input.id}`);
                   }}>
                  <TruthBadge truthClass={input.truthClass} />
                  <strong>version {input.ordinal}</strong>
                  <span className="quiet mono">{input.contentDigest.slice(0, 16)}…</span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <aside className="rail" aria-label="Evidence">
        <h2>Evidence</h2>
        <dl>
          <dt>Truth class</dt>
          <dd><TruthBadge truthClass={version.truthClass} /></dd>

          <dt>Coordinate reference</dt>
          <dd>EPSG:{version.crsEpsg}</dd>

          <dt>Vertical datum</dt>
          <dd>{version.verticalDatum}</dd>

          <dt>Extent</dt>
          <dd className="mono">
            {version.extent.west.toFixed(4)}, {version.extent.south.toFixed(4)}<br />
            {version.extent.east.toFixed(4)}, {version.extent.north.toFixed(4)}
          </dd>

          <dt>Measured</dt>
          <dd>{measuredOver}</dd>

          {version.clockOffsetSeconds === undefined ? null : (
            <>
              <dt>Instrument clock offset</dt>
              <dd>{version.clockOffsetSeconds} s from UTC</dd>
            </>
          )}

          <dt>Uncertainty</dt>
          <dd>{describeUncertainty(uncertainty)}</dd>

          <dt>Rights</dt>
          <dd>{version.rights}</dd>

          <dt>Attribution</dt>
          <dd>{version.attribution}</dd>

          <dt>Content digest</dt>
          <dd className="mono break">{version.contentDigest}</dd>

          <dt>Produced by</dt>
          <dd>
            {version.producerJobId ? (
              <a href={`/work/${version.producerJobId}`}
                 onClick={(event) => {
                   event.preventDefault();
                   navigate(`/work/${version.producerJobId}`);
                 }}>
                the job that computed it
              </a>
            ) : (
              "a person, who recorded it directly"
            )}
          </dd>

          {version.recipeId ? (
            <>
              <dt>Recipe</dt>
              <dd className="mono break">{version.recipeId}</dd>
              <dt>Image</dt>
              <dd className="mono break">{version.imageDigest}</dd>
            </>
          ) : null}

          <dt>Recorded</dt>
          <dd>{new Date(version.createdAt).toISOString().replace("T", " ").slice(0, 19)} UTC</dd>
        </dl>
      </aside>
    </div>
  );
}

function ManifestRow({ layerId, versionId, file }:
{ layerId: string; versionId: string; file: ManifestFile }) {
  const [readUrl, setReadUrl] = useState<string | undefined>();
  const [asking, setAsking] = useState(false);

  const ask = async () => {
    setAsking(true);
    try {
      const answer = await client.versionFile(layerId, versionId, file.relativePath);
      setReadUrl(answer.readUrl);
    } finally {
      setAsking(false);
    }
  };

  return (
    <tr>
      <td className="mono">{file.relativePath}</td>
      <td className="mono">{file.sha256.slice(0, 12)}…</td>
      <td>{file.sizeBytes.toLocaleString()} B</td>
      <td className="quiet">{file.mediaType}</td>
      <td>
        {readUrl ? (
          <a href={readUrl} rel="noreferrer">download</a>
        ) : (
          <button type="button" onClick={() => void ask()} disabled={asking}>
            {asking ? "asking…" : "get a link"}
          </button>
        )}
      </td>
    </tr>
  );
}
