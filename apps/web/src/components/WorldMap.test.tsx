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

const version = {
  id: "ver_1",
  layerId: "layer_1",
  ordinal: 3,
  contentDigest: "abc",
  truthClass: "analysis",
  crsEpsg: 4326,
  verticalDatum: "EGM2008 (EPSG:3855)",
  extent: { west: -180, south: -90, east: 180, north: 90 },
  observedFrom: "2022-01-01T00:00:00Z",
  observedTo: "2022-12-31T23:59:59Z",
  rights: "public domain",
  attribution: "NOAA NCEI",
  state: "published",
  visibility: "canonical",
  createdAt: "2026-08-28T00:00:00Z",
} as const;

describe("showing where places are", () => {
  it("says plainly when the world holds no basemap", () => {
    render(<WorldMap cities={[]} />);
    expect(
      screen.getByText(/No\s+bathymetry, terrain, or coastline layer is published/),
    ).toBeInTheDocument();
  });

  it("draws the basemap the shared world holds, and credits it", () => {
    const { container } = render(
      <WorldMap
        cities={[]}
        basemap={{
          imageUrl: "https://storage.example/elevation.png",
          version: { ...version },
          layerTitle: "Global bathymetry and topography",
          attribution: "NOAA NCEI",
        }}
      />,
    );
    expect(container.querySelector("image")).toHaveAttribute(
      "href",
      "https://storage.example/elevation.png",
    );
    expect(screen.getByText(/NOAA NCEI/)).toBeInTheDocument();
    // The distinction between the picture and the data behind it is the point.
    expect(screen.getByText(/is a rendering/)).toBeInTheDocument();
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
