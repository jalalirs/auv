// What the window is allowed to ask for.
//
// Each call is named for what it does and forwards to exactly one channel. No
// generic "send anything" is exposed, so the page cannot reach the main process
// beyond what is written here, and what is written here is typed once in
// shared/bridge.ts for both sides.

import { contextBridge, ipcRenderer } from "electron";

import { CHANNELS, type Bridge, type LatLon } from "../shared/bridge.js";

const bridge: Bridge = {
  ocean: {
    nearestSite: (at: LatLon, withinKm: number) =>
      ipcRenderer.invoke(CHANNELS.nearestSite, at, withinKm),
    record: (siteId: number, at: LatLon) =>
      ipcRenderer.invoke(CHANNELS.record, siteId, at),
  },
  app: {
    version: () => ipcRenderer.invoke(CHANNELS.version),
  },
};

contextBridge.exposeInMainWorld("coralCity", bridge);
