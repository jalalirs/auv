// The calls the window may make, answered here.
//
// One handler per channel in shared/bridge.ts. A handler validates what it is
// given before acting on it, because the renderer shows content the platform
// sent and is treated as if it could be wrong.

import { app, ipcMain, safeStorage, shell } from "electron";
import { promises as fs } from "node:fs";
import path from "node:path";

import { CHANNELS, type KeptSession, type LatLon } from "../shared/bridge.js";
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

  // Signing in with Google happens in the system browser, where the person's
  // Google session already is, never in this window.
  ipcMain.handle(CHANNELS.openGoogle, async (_event, address: unknown) => {
    const url = new URL(String(address));
    if ((url.protocol !== "https:" && url.protocol !== "http:")
        || url.pathname !== "/api/v1/auth/google/start") {
      throw new Error("not a Google sign-in address");
    }
    await shell.openExternal(url.toString());
  });

  // The sign-in, kept between launches so a restart or a reload does not ask
  // again. Encrypted by the system's keychain (Keychain, DPAPI, libsecret);
  // where there is none, nothing is kept and the person signs in each time.
  // The platform decides how long the session itself lasts.
  const sessionFile = path.join(app.getPath("userData"), "session.bin");
  ipcMain.handle(CHANNELS.keep, async (_event, session: unknown) => {
    const one = session as Partial<KeptSession> | undefined;
    if (typeof one?.base !== "string" || typeof one.token !== "string") throw new Error("not a session");
    if (!safeStorage.isEncryptionAvailable()) return;
    await fs.writeFile(sessionFile, safeStorage.encryptString(JSON.stringify({ base: one.base, token: one.token })), { mode: 0o600 });
  });
  ipcMain.handle(CHANNELS.kept, async (): Promise<KeptSession | undefined> => {
    try {
      if (!safeStorage.isEncryptionAvailable()) return undefined;
      const one = JSON.parse(safeStorage.decryptString(await fs.readFile(sessionFile))) as Partial<KeptSession>;
      return typeof one.base === "string" && typeof one.token === "string" ? { base: one.base, token: one.token } : undefined;
    } catch {
      return undefined;
    }
  });
  ipcMain.handle(CHANNELS.forget, async () => { await fs.rm(sessionFile, { force: true }); });
}
