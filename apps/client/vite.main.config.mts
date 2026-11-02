import { defineConfig } from "vite";

// The main process, as an ES module. The preload is built apart by
// vite.preload.config.mts: Electron runs it sandboxed, where only CommonJS
// loads and nothing but electron itself can be required.
export default defineConfig({
  build: {
    outDir: "dist/main",
    emptyOutDir: true,
    lib: {
      entry: { main: "src/main/main.ts" },
      formats: ["es"],
    },
    rollupOptions: { external: ["electron", /^node:/] },
  },
});
