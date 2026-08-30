import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "dist/main",
    emptyOutDir: true,
    lib: {
      entry: { main: "src/main/main.ts", preload: "src/main/preload.ts" },
      formats: ["es"],
    },
    rollupOptions: { external: ["electron", /^node:/] },
  },
});
