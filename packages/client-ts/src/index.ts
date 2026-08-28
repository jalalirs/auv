// The client the web application uses to talk to the platform.
//
// Every type here comes from the generated contract types, and every URL is
// checked against the contract's path list at compile time. Nothing describes
// the API a second time, so nothing can drift from it: an endpoint that is
// removed or renamed stops compiling here rather than failing in a browser.

import type { components, paths } from "./schema.js";

type Schemas = components["schemas"];

export type Problem = Schemas["Problem"]["error"];
export type Principal = Schemas["Principal"];
export type Organisation = Schemas["Organisation"];
export type City = Schemas["City"];
export type Layer = Schemas["Layer"];
export type Version = Schemas["Version"];
export type ManifestFile = Schemas["ManifestFile"];
export type Binding = Schemas["Binding"];
export type Denial = Schemas["Denial"];
export type Job = Schemas["Job"];
export type Attempt = Schemas["Attempt"];
export type JobEvent = Schemas["JobEvent"];
export type Quota = Schemas["Quota"];
export type Target = Schemas["Target"];
export type TruthClass = Schemas["TruthClass"];
export type Discoverability = Schemas["Discoverability"];
export type Uncertainty = Schemas["Uncertainty"];
export type Extent = Schemas["Extent"];
export type Role = Schemas["Role"];

/** Endpoint asserts at compile time that a path exists in the contract. */
type Endpoint = keyof paths;
const endpoint = <P extends Endpoint>(path: P): P => path;

/**
 * Refused is a failure the platform reported, carrying the code it used.
 *
 * The distinction the platform draws between refusals is meaningful and worth
 * preserving here: `notFound` may mean the object does not exist or that the
 * caller is not entitled to know it does, and the two are deliberately
 * indistinguishable.
 */
export class Refused extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string;
  readonly detail: Record<string, unknown>;

  constructor(status: number, problem: Partial<Problem>) {
    super(problem.message ?? "the platform refused this request");
    this.name = "Refused";
    this.status = status;
    this.code = problem.code ?? "unknown";
    this.requestId = problem.requestId ?? "";
    this.detail = (problem.detail as Record<string, unknown>) ?? {};
  }

  /** unauthenticated reports that nobody is signed in. */
  get unauthenticated(): boolean {
    return this.status === 401;
  }

  /** notFound reports absence, which may also mean "not yours to know about". */
  get notFound(): boolean {
    return this.status === 404;
  }

  /** accessMayBeRequested marks a refusal where asking is the next step. */
  get accessMayBeRequested(): boolean {
    return this.detail["accessMayBeRequested"] === true;
  }
}

interface Options {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
}

async function call<T>(path: string, options: Options = {}): Promise<T> {
  const url = new URL(path, globalThis.location?.origin ?? "http://localhost");
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }

  const response = await fetch(url.toString(), {
    method: options.method ?? "GET",
    // The session lives in a cookie the browser cannot read from script, so it
    // has to be sent explicitly rather than attached as a header.
    credentials: "same-origin",
    headers: options.body === undefined ? {} : { "content-type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const parsed: unknown = text.length === 0 ? undefined : JSON.parse(text);

  if (!response.ok) {
    const problem = (parsed as { error?: Partial<Problem> } | undefined)?.error ?? {};
    throw new Refused(response.status, problem);
  }
  return parsed as T;
}

const segment = (value: string): string => encodeURIComponent(value);

export const client = {
  /** platform identifies the build serving this request. */
  platform: () =>
    call<{ name: string; service: string; version: string; commit: string; builtAt: string }>(
      endpoint("/api/v1/platform"),
    ),

  /** signIn authenticates a person and starts a session. */
  signIn: (email: string, secret: string) =>
    call<{ token: string; expiresAt: string; principal: Principal }>(
      endpoint("/api/v1/sessions"),
      { method: "POST", body: { email, secret } },
    ),

  /** signOut ends the caller's own session. */
  signOut: () => call<void>(endpoint("/api/v1/sessions"), { method: "DELETE" }),

  /** me reports who the caller is and which institutions' bindings apply. */
  me: () =>
    call<{ principal: Principal; organisations: Organisation[] }>(endpoint("/api/v1/me")),

  /** denials reports the refusals the caller has received. */
  denials: (limit = 50) =>
    call<{ denials: Denial[] }>(endpoint("/api/v1/me/denials"), { query: { limit } }),

  /** catalogue lists the places the caller may learn of. */
  catalogue: () => call<{ cities: City[] }>(endpoint("/api/v1/cities")),

  /** city enters a place. */
  city: (cityId: string) =>
    call<{ city: City; you: { role?: Role } }>(
      `${endpoint("/api/v1/cities")}/${segment(cityId)}`,
    ),

  /** cityLayers lists the layers of a place that hold something visible. */
  cityLayers: (cityId: string) =>
    call<{ layers: Layer[] }>(`${endpoint("/api/v1/cities")}/${segment(cityId)}/layers`),

  /** cityGrants lists who has been granted access to a place. */
  cityGrants: (cityId: string) =>
    call<{ grants: Binding[] }>(`${endpoint("/api/v1/cities")}/${segment(cityId)}/grants`),

  /** worldLayers lists the layers of the shared world. */
  worldLayers: () => call<{ layers: Layer[] }>(endpoint("/api/v1/world/layers")),

  /** layer reads a layer and the versions the caller may see. */
  layer: (layerId: string) =>
    call<{ layer: Layer; versions: Version[] }>(
      `${endpoint("/api/v1/layers/{layerId}").replace("{layerId}", segment(layerId))}`,
    ),

  /** version reads one version, including its manifest. */
  version: (layerId: string, versionId: string) =>
    call<{ version: Version; uncertainty: Uncertainty }>(
      `/api/v1/layers/${segment(layerId)}/versions/${segment(versionId)}`,
    ),

  /** lineage reports what a version was derived from. */
  lineage: (layerId: string, versionId: string) =>
    call<{ derivedFrom: Version[] }>(
      `/api/v1/layers/${segment(layerId)}/versions/${segment(versionId)}/lineage`,
    ),

  /** versionFile issues a short-lived URL for one file of a version. */
  versionFile: (layerId: string, versionId: string, path: string) =>
    call<{ file: ManifestFile; readUrl: string }>(
      `/api/v1/layers/${segment(layerId)}/versions/${segment(versionId)}/files/${path
        .split("/")
        .map(segment)
        .join("/")}`,
    ),

  /** jobs lists an institution's work. */
  jobs: (orgId: string, limit = 50) =>
    call<{ jobs: Job[] }>(`/api/v1/organisations/${segment(orgId)}/jobs`, { query: { limit } }),

  /** job reads one job, every placement of it, and what it produced. */
  job: (jobId: string) =>
    call<{ job: Job; attempts: Attempt[]; outputs: Record<string, string> }>(
      `/api/v1/jobs/${segment(jobId)}`,
    ),

  /** jobEvents reads a job's account of itself from a point in the stream. */
  jobEvents: (jobId: string, after = 0, signal?: AbortSignal) =>
    call<{ events: JobEvent[] }>(`/api/v1/jobs/${segment(jobId)}/events`, {
      query: { after },
      signal,
    }),

  /** cancelJob stops work that has not finished. */
  cancelJob: (jobId: string) =>
    call<{ job: Job }>(`/api/v1/jobs/${segment(jobId)}/cancel`, { method: "POST", body: {} }),

  /** quota reports what an institution may consume and what it does. */
  quota: (orgId: string) =>
    call<{ quota: Quota; inUse: Record<string, number> }>(
      `/api/v1/organisations/${segment(orgId)}/quota`,
    ),
};

export type Client = typeof client;
