import { client, type Version } from "@coral-city/client";

import { useAsked, type Asked } from "./useAsync";

/** What the shared world offers as a backdrop, and where it came from. */
export interface Basemap {
  imageUrl: string;
  version: Version;
  layerTitle: string;
  attribution: string;
}

/** The file a bathymetry version carries for drawing, as opposed to measuring. */
const RENDERING = "elevation.png";

/**
 * Find the shared world's bathymetry, if it has any.
 *
 * The map draws only what the platform actually holds, so this returns nothing
 * until a bathymetry layer has been published — and the map says so plainly in
 * the meantime rather than inventing a coastline.
 *
 * What is drawn is the rendering the ingestion produced, never the grid beside
 * it: the grid is the data, and a picture of it is a picture.
 */
export function useBasemap(): Asked<Basemap | undefined> {
  return useAsked(async () => {
    const world = await client.worldLayers();
    const bathymetry = world.layers.find((layer) => layer.kind === "bathymetry");
    if (!bathymetry) return undefined;

    const held = await client.layer(bathymetry.id);
    const current = held.versions.find(
      (version) => version.state === "published" && version.visibility === "canonical",
    );
    if (!current) return undefined;

    // A listing of versions carries no manifests — a layer may hold many, and
    // each manifest may hold many files — so what this version contains has to
    // be asked for.
    const detail = await client.version(bathymetry.id, current.id);
    const drawn = (detail.version.manifest ?? []).find(
      (file) => file.relativePath === RENDERING,
    );
    if (!drawn) return undefined;

    const file = await client.versionFile(bathymetry.id, current.id, drawn.relativePath);
    return {
      imageUrl: file.readUrl,
      version: detail.version,
      layerTitle: bathymetry.title,
      attribution: current.attribution,
    };
  }, []);
}
