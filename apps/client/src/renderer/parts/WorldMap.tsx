// The Earth, from above, to choose a reef on.
//
// Satellite imagery rather than a street map: a reef is a colour in the
// water, and on a street map the sea is one flat blue. Tiles are Esri's World
// Imagery (credited in the corner, as its terms ask), drawn as images in a
// plain web-Mercator grid, so the application carries no map library for a
// page that needs a picture, a drag and a click.
//
// Drag to move, wheel to zoom, click to choose. The chosen point carries a
// square the size of the place it will become, so what is chosen is what will
// be built.

import { useEffect, useRef, useState } from "react";

const TILE = 256;
const TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile";
const CREDIT = "Imagery: Esri, Maxar, Earthstar Geographics";

export type LatLon = { lat: number; lon: number };

function worldPx(at: LatLon, zoom: number): { x: number; y: number } {
  const size = TILE * 2 ** zoom;
  const lat = Math.max(-85.05, Math.min(85.05, at.lat)) * Math.PI / 180;
  return {
    x: (at.lon + 180) / 360 * size,
    y: (1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2 * size,
  };
}

function latLonOf(px: { x: number; y: number }, zoom: number): LatLon {
  const size = TILE * 2 ** zoom;
  const lon = px.x / size * 360 - 180;
  const n = Math.PI - 2 * Math.PI * px.y / size;
  const lat = 180 / Math.PI * Math.atan(Math.sinh(n));
  return { lat, lon: ((lon + 540) % 360) - 180 };
}

/** Metres one screen pixel covers at a latitude and zoom. */
export function metresPerPixel(lat: number, zoom: number): number {
  return 156543.03392 * Math.cos(lat * Math.PI / 180) / 2 ** zoom;
}

export function WorldMap({ view, onView, chosen, onChoose, acrossM }: {
  view: { centre: LatLon; zoom: number };
  onView: (view: { centre: LatLon; zoom: number }) => void;
  chosen: LatLon | undefined;
  onChoose: (at: LatLon) => void;
  acrossM: number;
}): React.JSX.Element {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 520 });
  const drag = useRef<{ x: number; y: number; moved: number; centre: { x: number; y: number } } | undefined>(undefined);

  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const watch = new ResizeObserver(() => setSize({ w: element.clientWidth, h: element.clientHeight }));
    watch.observe(element);
    return () => watch.disconnect();
  }, []);

  const zoom = view.zoom;
  const centre = worldPx(view.centre, zoom);
  // Whole pixels, or the tiles' edges fall between pixels and show as seams.
  const left = Math.round(centre.x - size.w / 2), top = Math.round(centre.y - size.h / 2);
  const n = 2 ** zoom;
  const tiles: React.JSX.Element[] = [];
  for (let ty = Math.floor(top / TILE); ty <= Math.floor((top + size.h) / TILE); ty++) {
    if (ty < 0 || ty >= n) continue;
    for (let tx = Math.floor(left / TILE); tx <= Math.floor((left + size.w) / TILE); tx++) {
      const wrapped = ((tx % n) + n) % n;
      tiles.push(<img key={`${zoom}/${tx}/${ty}`} src={`${TILES}/${zoom}/${ty}/${wrapped}`} alt="" draggable={false}
                      style={{ position: "absolute", left: tx * TILE - left, top: ty * TILE - top,
                               width: TILE, height: TILE }} />);
    }
  }

  let square: React.JSX.Element | null = null;
  if (chosen) {
    const at = worldPx(chosen, zoom);
    const side = Math.max(6, acrossM / metresPerPixel(chosen.lat, zoom));
    square = (
      <div className="world-square" style={{ left: at.x - left - side / 2, top: at.y - top - side / 2,
                                             width: side, height: side }} />
    );
  }

  const pointer = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  return (
    <div ref={box} className="world-map"
         onPointerDown={(event) => {
           event.currentTarget.setPointerCapture(event.pointerId);
           const at = pointer(event);
           drag.current = { ...at, moved: 0, centre };
         }}
         onPointerMove={(event) => {
           const held = drag.current;
           if (!held) return;
           const at = pointer(event);
           const dx = at.x - held.x, dy = at.y - held.y;
           held.moved = Math.max(held.moved, Math.hypot(dx, dy));
           if (held.moved > 3) {
             onView({ centre: latLonOf({ x: held.centre.x - dx, y: held.centre.y - dy }, zoom), zoom });
           }
         }}
         onPointerUp={(event) => {
           const held = drag.current;
           drag.current = undefined;
           if (held && held.moved <= 3) {
             const at = pointer(event);
             onChoose(latLonOf({ x: left + at.x, y: top + at.y }, zoom));
           }
         }}
         onWheel={(event) => {
           const next = Math.max(2, Math.min(18, zoom + (event.deltaY < 0 ? 1 : -1)));
           if (next === zoom) return;
           // About the cursor, so what is under it stays under it.
           const rect = event.currentTarget.getBoundingClientRect();
           const at = { x: left + event.clientX - rect.left, y: top + event.clientY - rect.top };
           const under = latLonOf(at, zoom);
           const there = worldPx(under, next);
           const shift = { x: event.clientX - rect.left - size.w / 2, y: event.clientY - rect.top - size.h / 2 };
           onView({ centre: latLonOf({ x: there.x - shift.x, y: there.y - shift.y }, next), zoom: next });
         }}>
      {tiles}
      {square}
      <span className="world-credit">{CREDIT}</span>
      <div className="world-zoom">
        <button className="quiet" onClick={(e) => { e.stopPropagation(); onView({ ...view, zoom: Math.min(18, zoom + 1) }); }}
                onPointerDown={(e) => e.stopPropagation()}>+</button>
        <button className="quiet" onClick={(e) => { e.stopPropagation(); onView({ ...view, zoom: Math.max(2, zoom - 1) }); }}
                onPointerDown={(e) => e.stopPropagation()}>−</button>
      </div>
    </div>
  );
}
