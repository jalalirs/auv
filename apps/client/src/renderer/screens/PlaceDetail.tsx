// One place, in full.
//
// What its package says about it — where it is, how deep, what was surveyed
// and by whom, where a dive begins and why — and what the sea there is doing
// today. Every number here has a source on the page beside it.

import { useSea } from "../ocean/sea.js";
import { whereIs } from "../platform/packages.js";
import type { Held, Packages } from "./Deck.js";
import { Credit, Empty, PageHead, Pill, Row, SeaPanel, ago, fixed, useLoadedPicture } from "./parts.js";

export function PlaceDetail({ held, packages, id, onBack }: {
  held: Held;
  packages: Packages;
  id: string;
  onBack: () => void;
}): React.JSX.Element {
  const place = held.places.find((p) => p.id === id);
  const pkg = place === undefined ? undefined : packages.places.get(place.id);
  const site = pkg?.site;
  const at = place === undefined ? undefined : whereIs(place.extent, site);
  const sea = useSea(at);
  const picture = useLoadedPicture(pkg?.pictureUrl);

  if (place === undefined) {
    return <Empty title="Not a place you have">It may have been withdrawn, or you were never granted it.</Empty>;
  }

  const surveys = site?.from?.surveys?.map((s) => s.name).filter((n) => !n.startsWith("ETOPO")) ?? [];

  return (
    <>
      <PageHead title={place.name} says={place.summary} back="Places" onBack={onBack}
                aside={<Pill kind={place.discoverable ? "good" : undefined}>{place.discoverable ? "listed" : "unlisted"}</Pill>} />

      <section>
        <div className={`hero tall${picture ? " pictured" : ""}`}
             style={picture ? { backgroundImage: `url("${picture}")` } : undefined}>
          <div className="said">
            {picture ? null : <div className="eyebrow">no picture yet</div>}
          </div>
        </div>
        <Credit of={pkg?.credit} />
      </section>

      <div className="two">
        <section>
          <h2>The ground</h2>
          {pkg === undefined ? <p className="note">Reading the package…</p>
            : pkg === null ? <p className="note">This place has no published package.</p> : (
            <div className="kvs">
              <Row of="where" is={at ? `${at.latitude.toFixed(5)}, ${at.longitude.toFixed(5)}` : "not stated"}
                   note="From the platform's extent, or the package's own site record" />
              <Row of="across" is={site?.from?.acrossMetres ? `${site.from.acrossMetres.toFixed(0)} m square` : "—"} />
              <Row of="depth" is={site?.shallowestM !== undefined ? `${fixed(site.shallowestM, 1)} to ${fixed(site.deepestM, 1)} m` : "—"} />
              <Row of="datum" is={site?.datum ?? place.verticalDatum} />
              <Row of="ground" is={site?.from?.surveyed ? `surveyed, ${site.from.sampleMetres ?? "?"} m samples` : "constructed"}
                   note={site?.from?.source} />
              {surveys.length > 0 ? <Row of="surveys" is={surveys.join(", ")} /> : null}
              {site?.reef?.colonies ? (
                <Row of="reef" is={`${site.reef.colonies.toLocaleString()} colonies`} note={site.reef.source} />
              ) : null}
              {site?.reef?.kinds ? (
                <Row of="of which" is={Object.entries(site.reef.kinds).map(([k, n]) => `${n.toLocaleString()} ${k}`).join(", ")} />
              ) : null}
              <Row of="a dive begins" is={site?.beginAt ? `${site.beginAt[0]}, ${site.beginAt[1]} · ${(-site.beginAt[2]!).toFixed(1)} m down` : "at the middle"}
                   note={site?.beginBecause} />
              <Row of="layers" is={site?.layers ? Object.keys(site.layers).join(", ") : "—"} />
              <Row of="package" is={`version ${pkg.version.ordinal ?? "?"}${pkg.version.label ? ` · ${pkg.version.label}` : ""} · ${pkg.files.length} files · ${((pkg.version.totalBytes ?? 0) / 1e6).toFixed(0)} MB`}
                   note={pkg.version.digest} />
              <Row of="published" is={pkg.version.publishedAt ? ago(pkg.version.publishedAt) : "draft"} />
            </div>
          )}
        </section>

        <section>
          <h2>The sea, today</h2>
          <SeaPanel sea={sea} />
        </section>
      </div>
    </>
  );
}
