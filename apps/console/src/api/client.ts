// The client the console uses to talk to the control plane.
//
// Every type here comes from the generated contract types and every path is
// checked against the contract's path list at compile time. Nothing describes
// the API a second time, so nothing can drift from it: a route that is removed
// or renamed stops compiling here rather than failing in a browser.

import type { components, paths } from "./schema.js";

type Schemas = components["schemas"];

export type Problem = Schemas["Problem"]["error"];
export type Principal = Schemas["Principal"];
export type Organisation = Schemas["Organisation"];
export type City = Schemas["City"];
export type Vehicle = Schemas["Vehicle"];
export type AssetVersion = Schemas["AssetVersion"];
export type Queue = Schemas["Queue"];
export type Device = Schemas["Device"];
export type AutonomyStack = Schemas["AutonomyStack"];
export type Dive = Schemas["Dive"];
export type Run = Schemas["Run"];
export type Binding = Schemas["Binding"];
export type Denial = Schemas["Denial"];

/** A path the contract describes. Anything else does not compile. */
type Path = keyof paths;

/**
 * Refused carries what the platform said and why, because a refusal is often
 * the most informative answer a screen can give and flattening it into a
 * generic error throws that away.
 */
export class Refused extends Error {
  readonly status: number;
  readonly problem: Problem | undefined;

  constructor(status: number, problem: Problem | undefined) {
    super(problem?.message ?? `the platform answered ${status}`);
    this.name = "Refused";
    this.status = status;
    this.problem = problem;
  }

  /**
   * Whether the platform said this may be asked for. A hidden refusal reports
   * absence instead, and the two must not be shown the same way.
   */
  get mayBeRequested(): boolean {
    return this.problem?.detail?.accessMayBeRequested === true;
  }
}

async function request<T>(method: string, path: Path | string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    // The session is a cookie on this origin. No token is handed to script,
    // which is why nothing here reads or stores one.
    credentials: "same-origin",
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const parsed: unknown = text.length > 0 ? JSON.parse(text) : undefined;

  if (!response.ok) {
    const problem = (parsed as Schemas["Problem"] | undefined)?.error;
    throw new Refused(response.status, problem);
  }
  return parsed as T;
}

export const api = {
  platform: () => request<{ name: string; version: string; commit: string; builtAt: string }>(
    "GET", "/api/v1/platform"),

  signIn: (email: string, secret: string) =>
    request<{ principal: Principal; expiresAt: string }>(
      "POST", "/api/v1/sessions", { email, secret }),

  signOut: () => request<void>("DELETE", "/api/v1/sessions"),

  me: () => request<{ principal: Principal; organisations: Organisation[] }>(
    "GET", "/api/v1/me"),

  denials: () => request<{ denials: Denial[] }>("GET", "/api/v1/me/denials"),

  cities: () => request<{ cities: City[] }>("GET", "/api/v1/cities"),
  city: (id: string) => request<City>("GET", `/api/v1/cities/${id}`),
  cityVersions: (id: string) =>
    request<{ versions: AssetVersion[] }>("GET", `/api/v1/cities/${id}/versions`),
  cityGrants: (id: string) =>
    request<{ grants: Binding[] }>("GET", `/api/v1/cities/${id}/grants`),

  vehicles: () => request<{ vehicles: Vehicle[] }>("GET", "/api/v1/vehicles"),
  vehicle: (id: string) => request<Vehicle>("GET", `/api/v1/vehicles/${id}`),
  vehicleVersions: (id: string) =>
    request<{ versions: AssetVersion[] }>("GET", `/api/v1/vehicles/${id}/versions`),
  vehicleGrants: (id: string) =>
    request<{ grants: Binding[] }>("GET", `/api/v1/vehicles/${id}/grants`),

  queues: () => request<{ queues: Queue[] }>("GET", "/api/v1/queues"),
  queue: (id: string) => request<Queue>("GET", `/api/v1/queues/${id}`),
  devices: (id: string) => request<{ devices: Device[] }>("GET", `/api/v1/queues/${id}/devices`),
  queueGrants: (id: string) =>
    request<{ grants: Binding[] }>("GET", `/api/v1/queues/${id}/grants`),

  dives: (orgId: string) => request<{ dives: Dive[] }>(
    "GET", `/api/v1/organisations/${orgId}/dives`),
  dive: (id: string) => request<Dive>("GET", `/api/v1/dives/${id}`),
  runs: (diveId: string) => request<{ runs: Run[] }>("GET", `/api/v1/dives/${diveId}/runs`),
  autonomy: (orgId: string) =>
    request<{ autonomy: AutonomyStack[] }>("GET", `/api/v1/organisations/${orgId}/autonomy`),

  organisations: () =>
    request<{ organisations: Organisation[] }>("GET", "/api/v1/organisations"),
  people: () => request<{ people: Principal[] }>("GET", "/api/v1/people"),

  createOrganisation: (slug: string, name: string) =>
    request<Organisation>("POST", "/api/v1/organisations", { slug, name }),
  createPerson: (displayName: string, email: string, secret: string) =>
    request<Principal>("POST", "/api/v1/people", { displayName, email, secret }),
  addMember: (orgId: string, principalId: string) =>
    request<void>("POST", `/api/v1/organisations/${orgId}/members`, { principalId }),
  removeMember: (orgId: string, principalId: string) =>
    request<void>("DELETE", `/api/v1/organisations/${orgId}/members/${principalId}`),

  organisation: (id: string) =>
    request<{ organisation: Organisation; members: Principal[] }>(
      "GET", `/api/v1/organisations/${id}`),

  grantCity: (id: string, subjectKind: string, subjectId: string, role: string) =>
    request<Binding>("POST", `/api/v1/cities/${id}/grants`, { subjectKind, subjectId, role }),
  grantVehicle: (id: string, subjectKind: string, subjectId: string, role: string) =>
    request<Binding>("POST", `/api/v1/vehicles/${id}/grants`, { subjectKind, subjectId, role }),
  grantQueue: (id: string, subjectKind: string, subjectId: string, role: string) =>
    request<Binding>("POST", `/api/v1/queues/${id}/grants`, { subjectKind, subjectId, role }),
  revokeCityGrant: (cityId: string, bindingId: string) =>
    request<void>("DELETE", `/api/v1/cities/${cityId}/grants/${bindingId}`),
  revokeVehicleGrant: (vehicleId: string, bindingId: string) =>
    request<void>("DELETE", `/api/v1/vehicles/${vehicleId}/grants/${bindingId}`),
  revokeQueueGrant: (queueId: string, bindingId: string) =>
    request<void>("DELETE", `/api/v1/queues/${queueId}/grants/${bindingId}`),
};
