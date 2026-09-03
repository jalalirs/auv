// The calls the window may make, answered here.
//
// One handler per channel in shared/bridge.ts. A handler validates what it is
// given before acting on it, because the renderer shows content the platform
// sent and is treated as if it could be wrong.

import { app, ipcMain } from "electron";
import path from "node:path";

import { CHANNELS, type LatLon } from "../shared/bridge.js";
import { aqualink } from "./ocean/aqualink.js";

function asPoint(value: unknown): LatLon {
  const point = value as Partial<LatLon> | undefined;
  if (point === undefined
      || typeof point.latitude !== "number" || typeof point.longitude !== "number"
      || Math.abs(point.latitude) > 90 || Math.abs(point.longitude) > 180) {
    throw new Error("not a point on the globe");
  }
  return { latitude: point.latitude, longitude: point.longitude };
}

export function answerTheWindow(): void {
  const ocean = aqualink(path.join(app.getPath("userData"), "cache"));

  ipcMain.handle(CHANNELS.nearestSite, (_event, at: unknown, withinKm: unknown) =>
    ocean.nearestSite(asPoint(at), Math.min(200, Math.max(1, Number(withinKm) || 25))));

  ipcMain.handle(CHANNELS.record, (_event, siteId: unknown, at: unknown) => {
    const id = Number(siteId);
    if (!Number.isInteger(id) || id <= 0) throw new Error("not a site");
    return ocean.record(id, asPoint(at));
  });

  ipcMain.handle(CHANNELS.version, () => app.getVersion());
}
