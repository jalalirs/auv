// The last weeks of sea temperature, as a line.
//
// One line, the bleaching threshold as a rule across it, and the days above
// the rule shaded, because that is the one thing anybody reading a reef's
// temperature wants to see at a glance. Drawn as SVG so it is sharp at any
// size and needs no library.

import type { SeaDay } from "../../shared/bridge.js";

export function Chart({ days, threshold }: { days: SeaDay[]; threshold?: number }): React.JSX.Element | null {
  const known = days.filter((d) => d.satelliteTemperatureC !== undefined);
  if (known.length < 2) return null;
  const width = 640, height = 150, left = 34, right = 10, top = 10, bottom = 22;
  const values = known.map((d) => d.satelliteTemperatureC!);
  const lo = Math.floor(Math.min(...values, threshold ?? Infinity) - 0.5);
  const hi = Math.ceil(Math.max(...values, threshold ?? -Infinity) + 0.5);
  const x = (i: number): number => left + (i / (known.length - 1)) * (width - left - right);
  const y = (v: number): number => top + (1 - (v - lo) / (hi - lo)) * (height - top - bottom);
  const line = known.map((d, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(d.satelliteTemperatureC!).toFixed(1)}`).join(" ");
  const above = threshold === undefined ? "" : known
    .map((d, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(Math.max(d.satelliteTemperatureC!, threshold)).toFixed(1)}`)
    .join(" ") + ` L${x(known.length - 1).toFixed(1)},${y(threshold).toFixed(1)} L${x(0).toFixed(1)},${y(threshold).toFixed(1)} Z`;
  const ticks: number[] = [];
  for (let v = lo; v <= hi; v += (hi - lo) > 6 ? 2 : 1) ticks.push(v);
  const first = known[0]!.date, last = known[known.length - 1]!.date;
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img"
           aria-label={`Sea surface temperature from ${first} to ${last}`}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={left} x2={width - right} y1={y(v)} y2={y(v)} className="grid" />
            <text x={left - 6} y={y(v) + 3} className="tick">{v}°</text>
          </g>
        ))}
        {threshold === undefined ? null : (
          <>
            <path d={above} className="above" />
            <line x1={left} x2={width - right} y1={y(threshold)} y2={y(threshold)} className="threshold" />
            <text x={width - right} y={y(threshold) - 4} className="tick end">bleaching threshold</text>
          </>
        )}
        <path d={line} className="line" />
        <text x={left} y={height - 6} className="tick">{first}</text>
        <text x={width - right} y={height - 6} className="tick end">{last}</text>
      </svg>
      <figcaption>Sea surface temperature by satellite, daily, the last eight weeks.</figcaption>
    </figure>
  );
}
