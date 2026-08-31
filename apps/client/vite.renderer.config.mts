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
});
