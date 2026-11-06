// A big reef's colonies, as its package ships them: colonies.bin, written by
// the place build from the same arrays as the reef's point instancer, so row i
// is the instancer's colony i and is named coral-<i+1>.
//
// A million colonies are a population, not a list. The world does not carry
// them; it carries only the colonies somebody changed (moved, turned, grown,
// hidden, copied), and a dive takes those over the build as it is. Rows mean
// something only within one package version: a rebuild draws a fresh reef.
//
// The file, little-endian: "ICOL", a uint32 header length, the header as
// UTF-8 JSON padded with spaces to four bytes, then five columns: x, y, sizeM,
// builtDeg as float32 and form as uint8 indexing the header's forms.

import type { Item } from "./scene.js";
import type { WorldDocument } from "./world.js";

export interface Population {
  /** The package version the rows belong to. */
  version: string;
  digest: string;
  count: number;
  forms: string[];
  x: Float32Array;
  y: Float32Array;
  sizeM: Float32Array;
  builtDeg: Float32Array;
  form: Uint8Array;
}

export function readColonies(bytes: ArrayBuffer): Population {
  const view = new DataView(bytes);
  if (bytes.byteLength < 8 || String.fromCharCode(...new Uint8Array(bytes, 0, 4)) !== "ICOL") {
    throw new Error("not a colonies file");
  }
  const length = view.getUint32(4, true);
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(bytes, 8, length))) as {
    format?: number; version?: string; digest?: string; count?: number; forms?: string[];
  };
  if (header.format !== 1) throw new Error(`colonies file format ${header.format ?? "?"}, not 1`);
  const count = Number(header.count ?? 0);
  let at = 8 + length;
  if (at % 4 !== 0 || bytes.byteLength < at + count * 17) throw new Error("colonies file cut short");
  const column = () => { const one = new Float32Array(bytes, at, count); at += count * 4; return one; };
  const x = column(), y = column(), sizeM = column(), builtDeg = column();
  const form = new Uint8Array(bytes, at, count);
  return { version: String(header.version ?? ""), digest: String(header.digest ?? ""), count, forms: header.forms ?? [], x, y, sizeM, builtDeg, form };
}

/** The file for a population: what a place build writes, and what a test reads. */
export function writeColonies(p: Omit<Population, "count"> & { count?: number }): ArrayBuffer {
  const count = p.x.length;
  let json = JSON.stringify({ format: 1, version: p.version, digest: p.digest, count, forms: p.forms });
  while ((8 + new TextEncoder().encode(json).length) % 4 !== 0) json += " ";
  const head = new TextEncoder().encode(json);
  const out = new ArrayBuffer(8 + head.length + count * 17);
  const bytes = new Uint8Array(out);
  bytes.set([73, 67, 79, 76]);
  new DataView(out).setUint32(4, head.length, true);
  bytes.set(head, 8);
  let at = 8 + head.length;
  for (const column of [p.x, p.y, p.sizeM, p.builtDeg]) { new Float32Array(out, at, count).set(column); at += count * 4; }
  bytes.set(p.form, at);
  return out;
}

/** The row a colony's id names, or undefined for one that is not a built row. */
export function rowOf(id: string, count: number): number | undefined {
  const found = /^coral-(\d+)$/.exec(id);
  const row = found ? Number(found[1]) - 1 : -1;
  return row >= 0 && row < count ? row : undefined;
}

/** The colonies near a point, quickly: a grid of rows by cell. */
export class Near {
  readonly cell: number;
  private readonly cells = new Map<number, number[]>();
  private readonly west: number;
  private readonly south: number;
  private readonly across: number;

  constructor(readonly p: Population, cellM = 10) {
    this.cell = cellM;
    let west = Infinity, south = Infinity, east = -Infinity;
    for (let i = 0; i < p.count; i++) { west = Math.min(west, p.x[i]!); south = Math.min(south, p.y[i]!); east = Math.max(east, p.x[i]!); }
    this.west = Number.isFinite(west) ? west : 0;
    this.south = Number.isFinite(south) ? south : 0;
    this.across = Math.max(1, Math.ceil(((Number.isFinite(east) ? east : 0) - this.west) / cellM) + 1);
    for (let i = 0; i < p.count; i++) {
      const key = this.key(p.x[i]!, p.y[i]!);
      const list = this.cells.get(key);
      if (list) list.push(i); else this.cells.set(key, [i]);
    }
  }

  private key(x: number, y: number): number {
    return Math.floor((y - this.south) / this.cell) * this.across + Math.floor((x - this.west) / this.cell);
  }

  /** Every row within r metres of (x, y). */
  within(x: number, y: number, r: number, most = Infinity): number[] {
    const out: number[] = [];
    const reach = Math.ceil(r / this.cell);
    const ci = Math.floor((x - this.west) / this.cell), cj = Math.floor((y - this.south) / this.cell);
    for (let j = cj - reach; j <= cj + reach; j++) {
      for (let i = ci - reach; i <= ci + reach; i++) {
        if (i < 0 || i >= this.across) continue;
        for (const row of this.cells.get(j * this.across + i) ?? []) {
          if (Math.hypot(this.p.x[row]! - x, this.p.y[row]! - y) <= r) out.push(row);
          if (out.length >= most) return out;
        }
      }
    }
    return out;
  }

  /** The row nearest (x, y) within r metres. */
  nearest(x: number, y: number, r: number): number | undefined {
    let best: number | undefined, bestD = r;
    for (const row of this.within(x, y, r)) {
      const d = Math.hypot(this.p.x[row]! - x, this.p.y[row]! - y);
      if (d <= bestD) { best = row; bestD = d; }
    }
    return best;
  }
}

// ---------------------------------------------------------------- edits


/** A built row as an item of the reef, as it was built: chosen, it can be changed. */
export function colonyItem(p: Population, row: number, name: string): Item {
  return {
    id: `coral-${row + 1}`, kind: "coral", form: p.forms[p.form[row]!] ?? "massive", name,
    x: r3(p.x[row]!), y: r3(p.y[row]!), sizeM: r3(p.sizeM[row]!), headingDeg: 0, builtDeg: Math.round(p.builtDeg[row]!),
    built: true,
  };
}

/** Whether an item of a built row is still as it was built. */
export function untouched(t: Item, p: Population): boolean {
  const row = rowOf(t.id, p.count);
  if (row === undefined || t.hidden) return false;
  const near = (a: unknown, b: number) => Math.abs(Number(a) - b) < 1e-3;
  return near(t.x, p.x[row]!) && near(t.y, p.y[row]!) && near(t.sizeM, p.sizeM[row]!) && !Number(t.headingDeg ?? 0);
}

/** The world as a big reef's edits: only the colonies somebody changed, over
 *  the build they were changed on. Rows chosen and left alone are dropped. */
export function asEdits(document: WorldDocument, p: Population): WorldDocument {
  return {
    ...document,
    layers: document.layers.map((l) => l.kind !== "reef" ? l : {
      ...l,
      params: { ...(l.params ?? {}), colonyEdits: true, editedOn: p.version },
      items: (l.items ?? []).filter((t) => t.kind !== "coral" || !untouched(t, p)),
    }),
  };
}

const r3 = (v: number) => Math.round(v * 1000) / 1000;
