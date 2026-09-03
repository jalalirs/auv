import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const here = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  root: resolve(here, "src/renderer"),
  // Env files live with the application, not with the page.
  //
  // Absolute, deliberately. Vite resolves both `root` and `envDir` and a
  // relative envDir is taken against the root — so "." pointed back at
  // src/renderer, which is exactly where the file is not. The first attempt at
  // this looked as though it had worked, because the address it was supposed to
  // fill in was already there from a previous sign-in.
  envDir: here,
  // Relative, because the packaged application loads the page from a file and
  // absolute paths resolve against the filesystem root there rather than the
  // application.
  base: "./",
  build: { outDir: resolve(here, "dist/renderer"), emptyOutDir: true },
  // Only for looking at the page in a browser while building it. A browser
  // will not let a page on one origin call a platform on another, and the
  // packaged application has no such problem because it is not a page on an
  // origin. So the dev server forwards the API to whichever platform
  // CORAL_CITY_UPSTREAM names, and the page signs in to the dev server's own
  // address. Nothing of this is in the built application.
  server: process.env.CORAL_CITY_UPSTREAM === undefined ? undefined : {
    proxy: { "/api": { target: process.env.CORAL_CITY_UPSTREAM, changeOrigin: true } },
  },
});
