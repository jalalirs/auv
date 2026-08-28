import type { City } from "@coral-city/client";

interface Props {
  cities: City[];
  selected?: string;
  onSelect?: (cityId: string) => void;
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
 * This draws a graticule and the extent of every place the caller may learn of.
 * It deliberately draws no coastline, terrain, or bathymetry, because none is
 * connected yet: a basemap invented for appearance would be the one thing this
 * platform must never do. When a bathymetry layer exists in the shared world,
 * this is where it is drawn from.
 */
export function WorldMap({ cities, selected, onSelect }: Props) {
  return (
    <figure className="world">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img"
           aria-label={`A world map showing ${cities.length} place${cities.length === 1 ? "" : "s"}`}>
        <rect className="world-sea" x={0} y={0} width={WIDTH} height={HEIGHT} />

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
        Extents of the places you may see, drawn on a graticule. No bathymetry,
        terrain, or coastline layer is connected, so none is drawn.
      </figcaption>
    </figure>
  );
}
