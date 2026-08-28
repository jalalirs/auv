import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const controlPlane =
  process.env.CORAL_CITY_CONTROL_PLANE_URL ?? "http://127.0.0.1:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 4173,
    strictPort: true,
    proxy: {
      "/api": controlPlane,
      "/health": controlPlane,
    },
  },
  preview: {
    port: 4173,
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    restoreMocks: true,
  },
});
