// Talking to a Coral City platform from somewhere else.
//
// The console talks to the platform it is served from, so its session is a
// cookie and no token is ever handed to script. This is the other case: an
// application on somebody's laptop, talking to a box across a network, which
// cannot use a cookie on an origin it was not served from. It holds a token.
//
// Every type here comes from the generated contract. Nothing describes the API
// a second time, so nothing can drift from it.

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
export type Conditions = Schemas["Conditions"];
export type Dive = Schemas["Dive"];
export type Run = Schemas["Run"];

/**
 * One thing that happened during a run.
 *
 * Described inline in the contract rather than as a named schema, so it is
 * named here from the operation that returns it. Written this way — as the
 * element type of that response — so that a change to the contract's shape
 * still shows up as a compile error rather than being quietly wrong.
 */
type EventsResponse =
  paths["/api/v1/dives/{diveId}/runs/{runId}/events"]["get"]["responses"][200]["content"]["application/json"];

export type RunEvent = NonNullable<EventsResponse["events"]>[number];

/** A path the contract describes. Anything else does not compile. */
type Path = keyof paths;

/**
 * Refused carries what the platform said and why.
 *
 * A refusal is often the most informative answer, and flattening it into a
 * generic error throws that away — particularly the difference between "there
 * is no such thing" and "there is, and you have not been granted it", which the
 * platform is careful to keep and a client should not collapse.
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

  get mayBeRequested(): boolean {
    return this.problem?.detail?.accessMayBeRequested === true;
  }
}

/** Nothing answered at all — a box that is off, or a network that is not there. */
export class Unreachable extends Error {
  constructor(readonly where: string, cause: unknown) {
    super(`${where} did not answer`);
    this.name = "Unreachable";
    this.cause = cause;
  }
}

export class Platform {
  #base: string;
  #token: string | undefined;

  constructor(base: string, token?: string) {
    // Trailing slashes are dropped so that a person typing an address with one
    // and a person typing it without reach the same platform.
    this.#base = base.replace(/\/+$/, "");
    this.#token = token;
  }

  get address(): string {
    return this.#base;
  }

  get signedIn(): boolean {
    return this.#token !== undefined;
  }

  async #request<T>(method: string, path: Path | string, body?: unknown): Promise<T> {
    let response: Response;
    try {
      response = await fetch(this.#base + path, {
        method,
        headers: {
          ...(this.#token ? { authorization: `Bearer ${this.#token}` } : {}),
          ...(body === undefined ? {} : { "content-type": "application/json" }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (cause) {
      // Distinguished from a refusal on purpose. A platform that says no and a
      // platform that is not there are different problems with different
      // remedies, and a client that shows them the same way sends people to
      // check their password when their laptop is offline.
      throw new Unreachable(this.#base, cause);
    }

    if (response.status === 204) return undefined as T;
    const text = await response.text();
    const parsed = text ? JSON.parse(text) : undefined;
    if (!response.ok) {
      throw new Refused(response.status, parsed?.error);
    }
    return parsed as T;
  }

  // ── who you are ────────────────────────────────────────────────────────────

  static async signIn(base: string, email: string, secret: string): Promise<Platform> {
    const open = new Platform(base);
    const session = await open.#request<{ token: string }>(
      "POST", "/api/v1/sessions", { email, secret });
    return new Platform(base, session.token);
  }

  me(): Promise<{ principal: Principal; organisations: Organisation[] }> {
    return this.#request("GET", "/api/v1/me");
  }

  /**
   * The institution a dive is kept under.
   *
   * A principal does not carry one — membership is a relation, and somebody may
   * belong to several — so it is the first of the ones they belong to. When
   * that stops being good enough the answer is to let people choose, not to
   * invent a field on the principal.
   */
  async institution(): Promise<Organisation | undefined> {
    const { organisations } = await this.me();
    return organisations[0];
  }

  // ── what you have been granted ─────────────────────────────────────────────

  async places(): Promise<City[]> {
    const { cities } = await this.#request<{ cities: City[] }>("GET", "/api/v1/cities");
    return cities;
  }

  async vehicles(): Promise<Vehicle[]> {
    const { vehicles } = await this.#request<{ vehicles: Vehicle[] }>("GET", "/api/v1/vehicles");
    return vehicles;
  }

  async versionsOfPlace(city: string): Promise<AssetVersion[]> {
    const { versions } = await this.#request<{ versions: AssetVersion[] }>(
      "GET", `/api/v1/cities/${city}/versions`);
    return versions;
  }

  async versionsOfVehicle(vehicle: string): Promise<AssetVersion[]> {
    const { versions } = await this.#request<{ versions: AssetVersion[] }>(
      "GET", `/api/v1/vehicles/${vehicle}/versions`);
    return versions;
  }

  async queues(): Promise<Queue[]> {
    const { queues } = await this.#request<{ queues: Queue[] }>("GET", "/api/v1/queues");
    return queues;
  }

  async devices(queue: string): Promise<Device[]> {
    const { devices } = await this.#request<{ devices: Device[] }>(
      "GET", `/api/v1/queues/${queue}/devices`);
    return devices;
  }

  // ── going in ───────────────────────────────────────────────────────────────

  /**
   * Record the water a dive happens in.
   *
   * Constructed water names no instant, deliberately: saying when would claim
   * it was drawn from a measurement of the ocean at that moment, and it was
   * not. The platform refuses conditions that claim a provenance they lack, and
   * that refusal is the most important thing it says about any result.
   */
  defineConditions(organisation: string, conditions: {
    kind: "observed" | "constructed";
    name: string;
    observedAt?: string;
    parameters?: Record<string, unknown>;
  }): Promise<Conditions> {
    return this.#request("POST", `/api/v1/organisations/${organisation}/conditions`, conditions);
  }

  defineDive(organisation: string, dive: {
    name: string;
    cityVersionId: string;
    vehicleVersionId: string;
    conditionsId?: string;
    autonomyStackId?: string;
  }): Promise<Dive> {
    return this.#request("POST", `/api/v1/organisations/${organisation}/dives`, dive);
  }

  ask(dive: string, request: {
    queueId: string;
    mode: "interactive" | "batch";
    runtimeVersion: string;
  }): Promise<Run> {
    return this.#request("POST", `/api/v1/dives/${dive}/runs`, request);
  }

  /**
   * End a dive, or withdraw a request for one that has not started.
   *
   * The same call for both. Whether it had started is not something the person
   * pressing the button knows or should have to.
   */
  cancel(dive: string, run: string): Promise<void> {
    return this.#request("POST", `/api/v1/dives/${dive}/runs/${run}/cancel`);
  }

  async events(dive: string, run: string): Promise<RunEvent[]> {
    const { events } = await this.#request<{ events: RunEvent[] }>(
      "GET", `/api/v1/dives/${dive}/runs/${run}/events`);
    return events;
  }

  async runs(dive: string): Promise<Run[]> {
    const { runs } = await this.#request<{ runs: Run[] }>(
      "GET", `/api/v1/dives/${dive}/runs`);
    return runs;
  }
}
