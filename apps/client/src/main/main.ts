// iocean, on somebody's own machine.
//
// This process owns the window, answers the few things the window may ask it
// for, and nothing else. No CUDA here, no ROS, no world data — that is the
// whole point of a thin client, and the moment any of it creeps onto a laptop
// the platform has stopped being a platform.

import { app, BrowserWindow, nativeImage, shell } from "electron";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { CHANNELS } from "../shared/bridge.js";
import { answerTheWindow } from "./ipc.js";

const here = path.dirname(fileURLToPath(import.meta.url));
// The icon lives with the sources and is copied beside the built main process,
// so that the same path works from the checkout and from inside a package.
const icon = nativeImage.createFromPath(path.join(here, "../../assets/icon.png"));

// Signing in with Google comes back through iocean://signed-in?code=…, a
// one-minute single-use code the window trades for a session. One running copy
// receives it: a second launch (how Windows and Linux deliver the link) hands
// its argument to the first and leaves.
const SCHEME = "iocean";
if (process.defaultApp && process.argv.length >= 2) {
  app.setAsDefaultProtocolClient(SCHEME, process.execPath, [path.resolve(process.argv[1]!)]);
} else {
  app.setAsDefaultProtocolClient(SCHEME);
}
if (!app.requestSingleInstanceLock()) app.quit();

let waiting: string | undefined;

function handOff(link: string | undefined): void {
  if (link === undefined || !link.startsWith(`${SCHEME}://`)) return;
  let code: string | null = null;
  try {
    const url = new URL(link);
    if (url.hostname === "signed-in") code = url.searchParams.get("code");
  } catch {
    return;
  }
  if (!code) return;
  const window = BrowserWindow.getAllWindows()[0];
  if (window === undefined || window.webContents.isLoading()) {
    waiting = code;
    return;
  }
  window.webContents.send(CHANNELS.handoff, code);
  if (window.isMinimized()) window.restore();
  window.focus();
}

app.on("open-url", (event, link) => { event.preventDefault(); handOff(link); });
app.on("second-instance", (_event, argv) => handOff(argv.find((a) => a.startsWith(`${SCHEME}://`))));

function open(): void {
  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    // The title lives in the page, over the water, rather than in a bar above
    // it. An application you dive in should not have a strip of grey chrome at
    // the top of the sea.
    // Windows and Linux have no traffic lights to inset, so their own window
    // buttons are drawn over the same strip.
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "hidden",
    ...(process.platform === "darwin" ? {} : { titleBarOverlay: { color: "#04080F", symbolColor: "#E6EEF5", height: 28 } }),
    backgroundColor: "#04080F",
    show: false,
    icon,
    webPreferences: {
      preload: path.join(here, "preload.cjs"),
      // Nothing the renderer shows is authored by us alone — a place's name and
      // a vehicle's description come from the platform — so it gets no Node.
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // Shown when it has something to show. A window that appears empty and then
  // fills in reads as a slow application even when it is not.
  window.once("ready-to-show", () => window.show());
  // A link that arrived before the page could hear it.
  window.webContents.on("did-finish-load", () => {
    if (waiting === undefined) return;
    window.webContents.send(CHANNELS.handoff, waiting);
    waiting = undefined;
  });

  // Links go to the browser, not into this window. A dive should not be
  // navigable away from by anything the platform sends us.
  window.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });

  holdTheZoom(window);
  // Back and forward from the mouse's side buttons and a trackpad swipe, as
  // the page's own history (every page has an address: ui/router.ts).
  window.on("app-command", (_event, command) => {
    if (command === "browser-backward") window.webContents.navigationHistory.goBack();
    if (command === "browser-forward") window.webContents.navigationHistory.goForward();
  });
  window.on("swipe", (_event, direction) => {
    if (direction === "right") window.webContents.navigationHistory.goBack();
    if (direction === "left") window.webContents.navigationHistory.goForward();
  });

  void window.loadFile(path.join(here, "../renderer/index.html"));
}

// Zoom between 80% and 125%, in tenths, and no pinching. Past that the
// layouts are not designed and stop holding together: tables wrapped every
// cell and pushed their buttons off the side.
const ZOOM = { least: 0.8, most: 1.25, step: 0.1 };

function holdTheZoom(window: BrowserWindow): void {
  const contents = window.webContents;
  contents.on("did-finish-load", () => { void contents.setVisualZoomLevelLimits(1, 1); });
  contents.on("before-input-event", (event, input) => {
    if (input.type !== "keyDown" || !(input.meta || input.control)) return;
    const now = contents.getZoomFactor();
    let next: number | undefined;
    if (input.key === "=" || input.key === "+") next = now + ZOOM.step;
    else if (input.key === "-") next = now - ZOOM.step;
    else if (input.key === "0") next = 1;
    if (next === undefined) return;
    event.preventDefault();
    contents.setZoomFactor(Math.min(ZOOM.most, Math.max(ZOOM.least, Math.round(next * 100) / 100)));
  });
}

// The name names the folder this machine keeps the application's settings in
// — the platform it signs in to, the last place and vehicle chosen. It was
// "Coral City", and a machine that ran it then has its settings there: they
// are copied across once, before anything is read, so nobody is asked again.
// The old folder is left where it was.
app.setName("iocean");
carryTheOldSettings(path.join(app.getPath("appData"), "Coral City"), app.getPath("userData"));

void app.whenReady().then(() => {
  // A packaged application carries its icon in its bundle; one run from a
  // checkout carries Electron's, and shows a stranger's face in the dock until
  // told otherwise.
  if (process.platform === "darwin" && !icon.isEmpty()) app.dock?.setIcon(icon);
  answerTheWindow();
  open();
  handOff(process.argv.find((a) => a.startsWith(`${SCHEME}://`)));
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) open();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

function carryTheOldSettings(old: string, current: string): void {
  try {
    if (fs.existsSync(old) && !fs.existsSync(current)) fs.cpSync(old, current, { recursive: true });
  } catch (error) {
    console.warn(`iocean could not carry its settings over from ${old}:`, error);
  }
}
