import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  root: "src/renderer",
  // Relative, because the packaged application loads the page from a file and
  // absolute paths resolve against the filesystem root there rather than the
  // application.
  base: "./",
  build: { outDir: "../../dist/renderer", emptyOutDir: true },
});
