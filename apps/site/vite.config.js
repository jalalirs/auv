import { resolve } from "node:path";
import { defineConfig } from "vite";

// The iOcean product site: three static pages.
//
// Every page is listed because Vite builds only what it is given; a page left
// out works in dev and is missing from dist.
//
// IOCEAN_DOWNLOAD_BASE is where the installers and their manifest.json live.
// The desktop app's update feed must name the same host, or an install updates
// from somewhere the site never sent anyone.
//
// IOCEAN_PLATFORM_URL is the control plane the Google button signs in to; left
// unset, the site shows no sign-in at all.
export default defineConfig({
  base: process.env.IOCEAN_SITE_BASE ?? "/",
  define: {
    __IOCEAN_DOWNLOAD_BASE__: JSON.stringify(process.env.IOCEAN_DOWNLOAD_BASE ?? "/downloads"),
    __IOCEAN_PLATFORM_URL__: JSON.stringify((process.env.IOCEAN_PLATFORM_URL ?? "").replace(/\/$/, "")),
  },
  publicDir: "public",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        home: resolve(import.meta.dirname, "index.html"),
        privacy: resolve(import.meta.dirname, "privacy.html"),
        terms: resolve(import.meta.dirname, "terms.html"),
      },
    },
  },
  server: { port: 4180, strictPort: true },
});
