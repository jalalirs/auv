"""The platform, from a script.

Enough of the API to publish a controller and fly it: sign in, find a vehicle
and a place, register an autonomy stack, define a dive, run it, and wait for
what it said. Plain urllib, so the SDK depends on nothing to talk to it.

A session is kept in ~/.config/coral-city/session.json by `coral-city sign-in`
and read by everything else; CORAL_CITY_API and CORAL_CITY_TOKEN override it.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.error
import urllib.request

SESSION = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config")) / "coral-city" / "session.json"


class Refused(Exception):
    def __init__(self, status: int, body: str, method: str, path: str) -> None:
        super().__init__(f"{method} {path} -> {status}: {body[:300]}")
        self.status = status


class Platform:
    def __init__(self, api: str, token: str | None = None) -> None:
        self.api = api.rstrip("/")
        self.token = token

    # ── sessions ─────────────────────────────────────────────────────────────

    @classmethod
    def from_session(cls) -> "Platform":
        api = os.environ.get("CORAL_CITY_API")
        token = os.environ.get("CORAL_CITY_TOKEN")
        if api and token:
            return cls(api, token)
        if SESSION.exists():
            kept = json.loads(SESSION.read_text())
            return cls(api or kept["api"], token or kept["token"])
        raise SystemExit("not signed in: run `coral-city sign-in` first, or set CORAL_CITY_API and CORAL_CITY_TOKEN")

    def sign_in(self, email: str, secret: str) -> str:
        answer = self.call("POST", "/api/v1/sessions", {"email": email, "secret": secret})
        self.token = answer["token"]
        return self.token

    def keep(self) -> None:
        SESSION.parent.mkdir(parents=True, exist_ok=True)
        SESSION.write_text(json.dumps({"api": self.api, "token": self.token}))
        SESSION.chmod(0o600)

    # ── the wire ─────────────────────────────────────────────────────────────

    def call(self, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.api + path, data=data, method=method)
        request.add_header("content-type", "application/json")
        if self.token:
            request.add_header("authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as error:
            raise Refused(error.code, error.read().decode(errors="replace"), method, path) from None

    # ── who and where ────────────────────────────────────────────────────────

    def me(self) -> dict:
        return self.call("GET", "/api/v1/me")

    def organisation(self, slug_or_id: str | None = None) -> dict:
        mine = self.me()["organisations"]
        if not mine:
            raise SystemExit("you belong to no institution on this platform")
        if slug_or_id is None:
            return mine[0]
        for org in mine:
            if slug_or_id in (org["slug"], org["id"]):
                return org
        raise SystemExit(f"you are not a member of '{slug_or_id}' (you are of {', '.join(o['slug'] for o in mine)})")

    def vehicles(self) -> list[dict]:
        return self.call("GET", "/api/v1/vehicles").get("vehicles", [])

    def vehicle(self, slug: str) -> dict:
        for one in self.vehicles():
            if slug in (one.get("slug"), one.get("id")):
                return one
        raise SystemExit(f"no vehicle '{slug}' you can see")

    def vehicle_versions(self, vehicle_id: str) -> list[dict]:
        return self.call("GET", f"/api/v1/vehicles/{vehicle_id}/versions").get("versions", [])

    def cities(self) -> list[dict]:
        return self.call("GET", "/api/v1/cities").get("cities", [])

    def city(self, slug: str) -> dict:
        for one in self.cities():
            if slug in (one.get("slug"), one.get("id")):
                return one
        raise SystemExit(f"no place '{slug}' you can see")

    def city_versions(self, city_id: str) -> list[dict]:
        return self.call("GET", f"/api/v1/cities/{city_id}/versions").get("versions", [])

    @staticmethod
    def published(versions: list[dict]) -> dict:
        ready = [v for v in versions if v.get("state") in ("published", None)] or versions
        if not ready:
            raise SystemExit("no versions")
        return sorted(ready, key=lambda v: v.get("createdAt", ""))[-1]

    def dynamics(self, version_id: str) -> dict:
        return self.call("GET", f"/api/v1/versions/{version_id}/dynamics")

    def queues(self) -> list[dict]:
        return self.call("GET", "/api/v1/queues").get("queues", [])

    # ── autonomy ─────────────────────────────────────────────────────────────

    def autonomy(self, org_id: str) -> list[dict]:
        return self.call("GET", f"/api/v1/organisations/{org_id}/autonomy").get("autonomy", [])

    def register_autonomy(self, org_id: str, slug: str, name: str, repository: str, digest: str,
                          subscribes: list[str], publishes: list[str], wants_gpu: bool = False,
                          needs: dict | None = None) -> dict:
        body = {"slug": slug, "name": name, "imageRepository": repository, "imageDigest": digest,
                "subscribes": subscribes, "publishes": publishes, "wantsGpu": wants_gpu}
        if needs:
            body["needs"] = needs
        return self.call("POST", f"/api/v1/organisations/{org_id}/autonomy", body)

    def stack(self, org_id: str, slug_or_id: str) -> dict:
        """By id, or by slug — the newest build registered under it."""
        stacks = [s for s in self.autonomy(org_id) if slug_or_id in (s["slug"], s["id"])]
        if not stacks:
            raise SystemExit(f"no autonomy '{slug_or_id}' in this institution")
        return sorted(stacks, key=lambda s: s.get("createdAt", ""))[-1]

    # ── dives ────────────────────────────────────────────────────────────────

    def conditions(self, org_id: str, current: tuple[float, float] | None = None,
                   visibility_m: float | None = None) -> dict:
        """Constructed water: still by default, or with a current (metres per
        second, heading it flows towards) and a visibility."""
        parameters = {"currentMetresPerSecond": 0, "currentHeadingDeg": 0}
        name = "Still water"
        if current is not None and current[0] > 0:
            parameters = {"currentMetresPerSecond": float(current[0]), "currentHeadingDeg": float(current[1])}
            name = f"{current[0] / 0.5144:.1f} knots towards {current[1]:.0f}°"
        if visibility_m:
            parameters["visibilityM"] = float(visibility_m)
            name += f", {visibility_m:.0f} m visibility"
        return self.call("POST", f"/api/v1/organisations/{org_id}/conditions", {
            "kind": "constructed", "name": name, "parameters": parameters})

    def define_dive(self, org_id: str, name: str, city_version: str, vehicle_version: str,
                    conditions: str, stack: str | None, initial_state: dict | None = None,
                    objective: dict | None = None) -> dict:
        body = {"name": name, "cityVersionId": city_version, "vehicleVersionId": vehicle_version,
                "conditionsId": conditions}
        if stack:
            body["autonomyStackId"] = stack
        if initial_state:
            body["initialState"] = initial_state
        if objective:
            body["objective"] = objective
        return self.call("POST", f"/api/v1/organisations/{org_id}/dives", body)

    def run(self, dive_id: str, queue_id: str, mode: str = "batch",
            runtime: str = "isaac-6.0.1+oceansim", seed: int | None = None) -> dict:
        body = {"queueId": queue_id, "mode": mode, "runtimeVersion": runtime}
        if seed is not None:
            body["seed"] = int(seed)
        return self.call("POST", f"/api/v1/dives/{dive_id}/runs", body)

    def runs(self, dive_id: str) -> list[dict]:
        return self.call("GET", f"/api/v1/dives/{dive_id}/runs").get("runs", [])

    def events(self, dive_id: str, run_id: str) -> list[dict]:
        return self.call("GET", f"/api/v1/dives/{dive_id}/runs/{run_id}/events").get("events", [])

    def artefacts(self, dive_id: str, run_id: str) -> list[dict]:
        """What a run left behind, each file with a link that fetches it."""
        return self.call("GET", f"/api/v1/dives/{dive_id}/runs/{run_id}/artefacts").get("artefacts", [])

    def fetch(self, dive_id: str, run_id: str, into, tell=None) -> int:
        """Download a run's recording into a directory. Returns how many files."""
        import pathlib
        import urllib.request
        into = pathlib.Path(into)
        count = 0
        for artefact in self.artefacts(dive_id, run_id):
            target = into / artefact["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(artefact["url"], timeout=60) as response:
                target.write_bytes(response.read())
            count += 1
            if tell is not None:
                tell(artefact["path"], artefact["sizeBytes"])
        return count

    def cancel(self, dive_id: str, run_id: str) -> None:
        self.call("POST", f"/api/v1/dives/{dive_id}/runs/{run_id}/cancel")

    def wait(self, dive_id: str, run_id: str, timeout: float = 900.0, tell=None,
             until_state=("succeeded", "failed", "expired", "cancelled")) -> dict:
        """Poll until the run is over, telling `tell` each new event."""
        seen = 0
        began = time.time()
        while time.time() - began < timeout:
            events = self.events(dive_id, run_id)
            for event in events[seen:]:
                if tell is not None:
                    tell(event)
            seen = len(events)
            run = next((r for r in self.runs(dive_id) if r["id"] == run_id), None)
            if run is not None and run.get("state") in until_state:
                return run
            time.sleep(3.0)
        raise TimeoutError(f"run {run_id} still not over after {timeout:.0f} s")
