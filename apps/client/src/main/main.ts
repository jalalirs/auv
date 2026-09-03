// Coral City, on somebody's own machine.
//
// This process owns the window, answers the few things the window may ask it
// for, and nothing else. No CUDA here, no ROS, no world data — that is the
// whole point of a thin client, and the moment any of it creeps onto a laptop
// the platform has stopped being a platform.

import { app, BrowserWindow, nativeImage, shell } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { answerTheWindow } from "./ipc.js";

const here = path.dirname(fileURLToPath(import.meta.url));
// The icon lives with the sources and is copied beside the built main process,
// so that the same path works from the checkout and from inside a package.
const icon = nativeImage.createFromPath(path.join(here, "../../assets/icon.png"));

function open(): void {
  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 960,
    minHeight: 640,
    // The title lives in the page, over the water, rather than in a bar above
    // it. An application you dive in should not have a strip of grey chrome at
    // the top of the sea.
    titleBarStyle: "hiddenInset",
    backgroundColor: "#04080F",
    show: false,
    icon,
    webPreferences: {
      preload: path.join(here, "preload.js"),
      // Nothing the renderer shows is authored by us alone — a place's name and
      // a vehicle's description come from the platform — so it gets no Node.
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // Shown when it has something to show. A window that appears empty and then
  // fills in reads as a slow application even when it is not.
  window.once("ready-to-show", () => window.show());

  // Links go to the browser, not into this window. A dive should not be
  // navigable away from by anything the platform sends us.
  window.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });

  void window.loadFile(path.join(here, "../renderer/index.html"));
}

app.setName("Coral City");

void app.whenReady().then(() => {
  // A packaged application carries its icon in its bundle; one run from a
  // checkout carries Electron's, and shows a stranger's face in the dock until
  // told otherwise.
  if (process.platform === "darwin" && !icon.isEmpty()) app.dock?.setIcon(icon);
  answerTheWindow();
  open();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) open();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
