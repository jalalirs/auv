// The client the console uses to talk to the control plane.
//
// Every type here comes from the generated contract types and every path is
// checked against the contract's path list at compile time. Nothing describes
// the API a second time, so nothing can drift from it: a route that is removed
// or renamed stops compiling here rather than failing in a browser.
/**
 * Refused carries what the platform said and why, because a refusal is often
 * the most informative answer a screen can give and flattening it into a
 * generic error throws that away.
 */
export class Refused extends Error {
    status;
    problem;
    constructor(status, problem) {
        super(problem?.message ?? `the platform answered ${status}`);
        this.name = "Refused";
        this.status = status;
        this.problem = problem;
    }
    /**
     * Whether the platform said this may be asked for. A hidden refusal reports
     * absence instead, and the two must not be shown the same way.
     */
    get mayBeRequested() {
        return this.problem?.detail?.accessMayBeRequested === true;
    }
}
async function request(method, path, body) {
    const response = await fetch(path, {
        method,
        // The session is a cookie on this origin. No token is handed to script,
        // which is why nothing here reads or stores one.
        credentials: "same-origin",
        headers: body === undefined ? {} : { "content-type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 204)
        return undefined;
    const text = await response.text();
    const parsed = text.length > 0 ? JSON.parse(text) : undefined;
    if (!response.ok) {
        const problem = parsed?.error;
        throw new Refused(response.status, problem);
    }
    return parsed;
}
export const api = {
    platform: () => request("GET", "/api/v1/platform"),
    signIn: (email, secret) => request("POST", "/api/v1/sessions", { email, secret }),
    signOut: () => request("DELETE", "/api/v1/sessions"),
    me: () => request("GET", "/api/v1/me"),
    denials: () => request("GET", "/api/v1/me/denials"),
    cities: () => request("GET", "/api/v1/cities"),
    city: (id) => request("GET", `/api/v1/cities/${id}`),
    cityVersions: (id) => request("GET", `/api/v1/cities/${id}/versions`),
    cityGrants: (id) => request("GET", `/api/v1/cities/${id}/grants`),
    vehicles: () => request("GET", "/api/v1/vehicles"),
    vehicle: (id) => request("GET", `/api/v1/vehicles/${id}`),
    vehicleVersions: (id) => request("GET", `/api/v1/vehicles/${id}/versions`),
    vehicleGrants: (id) => request("GET", `/api/v1/vehicles/${id}/grants`),
    queues: () => request("GET", "/api/v1/queues"),
    queue: (id) => request("GET", `/api/v1/queues/${id}`),
    devices: (id) => request("GET", `/api/v1/queues/${id}/devices`),
    queueGrants: (id) => request("GET", `/api/v1/queues/${id}/grants`),
    dives: (orgId) => request("GET", `/api/v1/organisations/${orgId}/dives`),
    dive: (id) => request("GET", `/api/v1/dives/${id}`),
    runs: (diveId) => request("GET", `/api/v1/dives/${diveId}/runs`),
    /**
     * End a dive, or withdraw a request for one that has not started.
     *
     * One call for both, because from here they are the same act — "I no longer
     * want this" — and which it turns out to be depends on whether a machine
     * happened to be free a second ago. Nobody should have to know that to stop
     * something they started.
     */
    cancelRun: (diveId, runId) => request("POST", `/api/v1/dives/${diveId}/runs/${runId}/cancel`),
    autonomy: (orgId) => request("GET", `/api/v1/organisations/${orgId}/autonomy`),
    organisations: () => request("GET", "/api/v1/organisations"),
    people: () => request("GET", "/api/v1/people"),
    createOrganisation: (slug, name) => request("POST", "/api/v1/organisations", { slug, name }),
    createPerson: (displayName, email, secret) => request("POST", "/api/v1/people", { displayName, email, secret }),
    addMember: (orgId, principalId) => request("POST", `/api/v1/organisations/${orgId}/members`, { principalId }),
    removeMember: (orgId, principalId) => request("DELETE", `/api/v1/organisations/${orgId}/members/${principalId}`),
    organisation: (id) => request("GET", `/api/v1/organisations/${id}`),
    grantCity: (id, subjectKind, subjectId, role) => request("POST", `/api/v1/cities/${id}/grants`, { subjectKind, subjectId, role }),
    grantVehicle: (id, subjectKind, subjectId, role) => request("POST", `/api/v1/vehicles/${id}/grants`, { subjectKind, subjectId, role }),
    grantQueue: (id, subjectKind, subjectId, role) => request("POST", `/api/v1/queues/${id}/grants`, { subjectKind, subjectId, role }),
    revokeCityGrant: (cityId, bindingId) => request("DELETE", `/api/v1/cities/${cityId}/grants/${bindingId}`),
    revokeVehicleGrant: (vehicleId, bindingId) => request("DELETE", `/api/v1/vehicles/${vehicleId}/grants/${bindingId}`),
    revokeQueueGrant: (queueId, bindingId) => request("DELETE", `/api/v1/queues/${queueId}/grants/${bindingId}`),
};
