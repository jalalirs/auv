// Aqualink, read from the main process.
//
// Fetched here rather than from the page for two reasons. The page is served
// from a file and a browser will not let it read a third-party API from there;
// and the site list is six thousand entries and five megabytes, which is worth
// keeping on disk for a day rather than pulling every time somebody opens the
// places page. The reading itself is in shared/aqualink.ts; this gives it a
// fetch and a file.

import { promises as fs } from "node:fs";
import path from "node:path";

import { AqualinkReader, type ListedSite, type SiteListStore } from "../../shared/aqualink.js";

const AGENT = "coral-city client";

class FileStore implements SiteListStore {
  #file: string;

  constructor(cacheDir: string) {
    this.#file = path.join(cacheDir, "aqualink-sites.json");
  }

  async read(): Promise<{ at: number; sites: ListedSite[] } | undefined> {
    try {
      const stat = await fs.stat(this.#file);
      return { at: stat.mtimeMs, sites: JSON.parse(await fs.readFile(this.#file, "utf8")) as ListedSite[] };
    } catch {
      return undefined;   // not cached yet, or unreadable: fetched afresh
    }
  }

  async write(sites: ListedSite[]): Promise<void> {
    await fs.mkdir(path.dirname(this.#file), { recursive: true });
    await fs.writeFile(this.#file, JSON.stringify(sites));
  }
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { "user-agent": AGENT } });
  if (!response.ok) throw new Error(`Aqualink answered ${response.status} for ${url}`);
  return response.json() as Promise<T>;
}

export function aqualink(cacheDir: string): AqualinkReader {
  return new AqualinkReader(fetchJson, new FileStore(cacheDir));
}
