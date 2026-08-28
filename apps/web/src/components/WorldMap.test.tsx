import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { City } from "@coral-city/client";

import { WorldMap } from "./WorldMap";

const place = (id: string, extent: City["extent"]): City => ({
  id,
  slug: id,
  name: `Place ${id}`,
  summary: "",
  extent,
  crsEpsg: 4326,
  verticalDatum: "mean sea level",
  discoverability: "listed_open",
  createdAt: "2026-01-01T00:00:00Z",
  createdBy: "prin_1",
});

describe("showing where places are", () => {
  it("says plainly that no basemap is connected", () => {
    render(<WorldMap cities={[]} />);
    expect(
      screen.getByText(/No bathymetry, terrain, or coastline layer is connected/),
    ).toBeInTheDocument();
  });

  it("draws every place it is given", () => {
    const { container } = render(
      <WorldMap
        cities={[
          place("a", { west: 38.9, south: 22.2, east: 39.1, north: 22.4 }),
          place("b", { west: -80, south: 24, east: -79, north: 25 }),
        ]}
      />,
    );
    expect(container.querySelectorAll(".place")).toHaveLength(2);
  });

  it("keeps a survey-scale extent large enough to aim at", () => {
    // A reef is a fraction of a pixel at world scale. Drawing it to true size
    // would make it invisible, so the mark has a floor and the real extent is
    // reported as a number elsewhere.
    const { container } = render(
      <WorldMap cities={[place("a", { west: 38.9, south: 22.2, east: 38.91, north: 22.21 })]} />,
    );
    const mark = container.querySelector(".place rect");
    expect(Number(mark?.getAttribute("width"))).toBeGreaterThanOrEqual(7);
    expect(Number(mark?.getAttribute("height"))).toBeGreaterThanOrEqual(7);
  });
});
