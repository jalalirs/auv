import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The console is served by nginx beside the control plane, which proxies the
// API on the same origin so that the session cookie is sent and no token is
// ever handed to script. In development the same is arranged by proxying here.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: process.env.CORAL_CITY_API ?? "http://127.0.0.1:18080",
        changeOrigin: false,
      },
    },
  },
});
