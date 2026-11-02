import { defineConfig } from "vite";

// The preload, as one CommonJS file with the bridge's channel names inlined. A
// sandboxed preload cannot import another chunk or load an ES module; when it
// fails, the page simply has no window.coralCity and cannot sign in.
export default defineConfig({
  build: {
    outDir: "dist/main",
    emptyOutDir: false,
    lib: {
      entry: { preload: "src/main/preload.ts" },
      formats: ["cjs"],
      fileName: () => "preload.cjs",
    },
    rollupOptions: { external: ["electron"] },
  },
});
