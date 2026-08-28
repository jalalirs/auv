import { client, type City } from "@coral-city/client";

import { Empty, Failure, Loading, Refusal } from "../components/Shell";
import { WorldMap } from "../components/WorldMap";
import { useBasemap } from "../basemap";
import { navigate } from "../router";
import { useAsked } from "../useAsync";

const discoverability: Record<City["discoverability"], string> = {
  listed_open: "open — anyone signed in may enter",
  listed_locked: "locked — access may be requested",
  unlisted: "unlisted — visible only to those bound to it",
};

export function Catalogue() {
  const asked = useAsked(() => client.catalogue(), []);
  const basemap = useBasemap();

  if (asked.loading) return <Loading what="the catalogue" />;
  if (asked.refusal) return <Refusal refusal={asked.refusal} />;
  if (asked.error) return <Failure error={asked.error} />;

  const cities = asked.value?.cities ?? [];

  return (
    <div className="page">
      <header className="page-head">
        <h1>Places</h1>
        <p className="quiet">
          Bounded, curated regions of the ocean. A place exists at the platform
          and outlives the institutions granted access to it.
        </p>
      </header>

      <WorldMap cities={cities} basemap={basemap.value}
                onSelect={(cityId) => navigate(`/cities/${cityId}`)} />

      {cities.length === 0 ? (
        <Empty>
          No place is visible to you. Places you have not been granted access to
          are not listed here, and unlisted places are not listed at all.
        </Empty>
      ) : (
        <ul className="cards">
          {cities.map((city) => (
            <li key={city.id}>
              <a href={`/cities/${city.id}`}
                 onClick={(event) => { event.preventDefault(); navigate(`/cities/${city.id}`); }}>
                <h2>{city.name}</h2>
                <p>{city.summary}</p>
                <dl className="facts">
                  <div><dt>Access</dt><dd>{discoverability[city.discoverability]}</dd></div>
                  <div><dt>Reference</dt><dd>EPSG:{city.crsEpsg}</dd></div>
                  <div><dt>Vertical datum</dt><dd>{city.verticalDatum}</dd></div>
                  <div>
                    <dt>Extent</dt>
                    <dd>
                      {city.extent.west.toFixed(4)}, {city.extent.south.toFixed(4)} to{" "}
                      {city.extent.east.toFixed(4)}, {city.extent.north.toFixed(4)}
                    </dd>
                  </div>
                </dl>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
