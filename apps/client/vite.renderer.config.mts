import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  root: "src/renderer",
  // Env files live with the application, not with the page. Vite looks for them
  // beside `root` by default, which is two directories in — so the local file
  // holding development credentials was never read, and the address that did
  // appear came from what a previous sign-in had remembered.
  envDir: ".",
  // Relative, because the packaged application loads the page from a file and
  // absolute paths resolve against the filesystem root there rather than the
  // application.
  base: "./",
  build: { outDir: "../../dist/renderer", emptyOutDir: true },
});
