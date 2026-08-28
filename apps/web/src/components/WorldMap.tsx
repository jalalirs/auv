import type { City } from "@coral-city/client";

import type { Basemap } from "../basemap";

interface Props {
  cities: City[];
  selected?: string;
  onSelect?: (cityId: string) => void;
  /** What the shared world offers as a backdrop, if it holds any. */
  basemap?: Basemap;
}

const WIDTH = 720;
const HEIGHT = 360;

/** Equirectangular projection: two degrees of longitude to one unit of width. */
const project = (longitude: number, latitude: number) => ({
  x: ((longitude + 180) / 360) * WIDTH,
  y: ((90 - latitude) / 180) * HEIGHT,
});

/**
 * Where the platform's places are.
 *
 * The backdrop is whatever the shared world actually holds: the rendering that
 * came with a published bathymetry version, credited to whoever published it.
 * When the world holds none, the map says so instead of inventing a coastline,
 * because a basemap drawn for appearance would be the one thing this platform
 * must never do.
 */
export function WorldMap({ cities, selected, onSelect, basemap }: Props) {
  return (
    <figure className="world">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img"
           aria-label={
             basemap
               ? `A world map of ${basemap.layerTitle}, showing ${cities.length} place${cities.length === 1 ? "" : "s"}`
               : `A world map showing ${cities.length} place${cities.length === 1 ? "" : "s"}`
           }>
        {basemap ? (
          <image href={basemap.imageUrl} x={0} y={0} width={WIDTH} height={HEIGHT}
                 preserveAspectRatio="none" />
        ) : (
          <rect className="world-sea" x={0} y={0} width={WIDTH} height={HEIGHT} />
        )}

        {[-60, -30, 0, 30, 60].map((latitude) => {
          const { y } = project(0, latitude);
          return (
            <g key={`lat-${latitude}`}>
              <line className={latitude === 0 ? "graticule equator" : "graticule"}
                    x1={0} y1={y} x2={WIDTH} y2={y} />
              <text className="graticule-label" x={4} y={y - 4}>
                {latitude === 0 ? "0°" : `${Math.abs(latitude)}°${latitude > 0 ? "N" : "S"}`}
              </text>
            </g>
          );
        })}
        {[-120, -60, 0, 60, 120].map((longitude) => {
          const { x } = project(longitude, 0);
          return (
            <line key={`lon-${longitude}`} className="graticule"
                  x1={x} y1={0} x2={x} y2={HEIGHT} />
          );
        })}

        {cities.map((city) => {
          const topLeft = project(city.extent.west, city.extent.north);
          const bottomRight = project(city.extent.east, city.extent.south);
          // A survey-scale extent is far smaller than a pixel at world scale,
          // so it is drawn at a size a person can actually aim at, and the
          // stated extent is shown as a number instead of implied by the mark.
          const width = Math.max(bottomRight.x - topLeft.x, 7);
          const height = Math.max(bottomRight.y - topLeft.y, 7);
          const isSelected = city.id === selected;
          return (
            <g key={city.id}
               className={isSelected ? "place place-selected" : "place"}
               onClick={() => onSelect?.(city.id)}
               role={onSelect ? "button" : undefined}
               tabIndex={onSelect ? 0 : undefined}
               onKeyDown={(event) => {
                 if (event.key === "Enter" || event.key === " ") onSelect?.(city.id);
               }}>
              <title>{`${city.name} — ${city.discoverability.replace("_", " ")}`}</title>
              <rect x={topLeft.x - width / 2} y={topLeft.y - height / 2}
                    width={width} height={height} rx={2} />
            </g>
          );
        })}
      </svg>
      <figcaption>
        {basemap ? (
          <>
            Extents of the places you may see, over{" "}
            <strong>{basemap.layerTitle}</strong>, version {basemap.version.ordinal},
            measured {basemap.version.observedFrom.slice(0, 4)}. {basemap.attribution}.
            The image is a rendering; the grid it was rendered from is in the same
            version and is what anyone measuring anything should read.
          </>
        ) : (
          <>
            Extents of the places you may see, drawn on a graticule. No
            bathymetry, terrain, or coastline layer is published in the shared
            world, so none is drawn.
          </>
        )}
      </figcaption>
    </figure>
  );
}
