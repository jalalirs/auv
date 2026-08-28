import { client } from "@coral-city/client";

import { Empty, Failure, Loading, Refusal } from "../components/Shell";
import { WorldMap } from "../components/WorldMap";
import { useBasemap } from "../basemap";
import { navigate } from "../router";
import { useAsked } from "../useAsync";

export function City({ cityId }: { cityId: string }) {
  const place = useAsked(() => client.city(cityId), [cityId]);
  const layers = useAsked(() => client.cityLayers(cityId), [cityId]);
  const basemap = useBasemap();

  if (place.loading) return <Loading what="this place" />;
  if (place.refusal) return <Refusal refusal={place.refusal} />;
  if (place.error) return <Failure error={place.error} />;
  if (!place.value) return null;

  const { city, you } = place.value;

  return (
    <div className="page">
      <header className="page-head">
        <p className="crumb">
          <a href="/" onClick={(event) => { event.preventDefault(); navigate("/"); }}>Places</a>
        </p>
        <h1>{city.name}</h1>
        <p>{city.summary}</p>
        <dl className="facts inline">
          <div><dt>Reference</dt><dd>EPSG:{city.crsEpsg}</dd></div>
          <div><dt>Vertical datum</dt><dd>{city.verticalDatum}</dd></div>
          <div><dt>Access</dt><dd>{city.discoverability.replace("_", " ")}</dd></div>
          <div><dt>Your authority here</dt><dd>{you.role ?? "none"}</dd></div>
        </dl>
      </header>

      <WorldMap cities={[city]} selected={city.id} basemap={basemap.value} />

      <section>
        <h2>Layers</h2>
        <p className="quiet">
          Everything this place holds. A layer is contained by the place and
          attributed to the institution that contributed it; a layer holding
          nothing you may see does not appear.
        </p>

        {layers.loading ? <Loading what="the layers" /> : null}
        {layers.refusal ? <Refusal refusal={layers.refusal} /> : null}
        {layers.value && layers.value.layers.length === 0 ? (
          <Empty>Nothing has been contributed to this place that you may see.</Empty>
        ) : null}

        <ul className="rows">
          {(layers.value?.layers ?? []).map((layer) => (
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
      </section>
    </div>
  );
}
