"""The platform, over HTTP, with nothing clever in it.

A thin client rather than a generated one on purpose: the TypeScript client in
`packages/api` is generated from the contract and the application depends on it,
and a second generated client is a second thing to keep in step. This reaches
for a handful of routes and says plainly which ones, so when the contract moves
the failure is a 404 with a route in it rather than a type error three builds
away.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class Refused(Exception):
    """The platform said no, and said why.

    Kept distinct from a transport failure because they are different facts: a
    refusal is the platform working correctly and an agent should read the
    reason and change what it asked for, and a timeout is nothing of the kind.
    """

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class Platform:
    """A signed-in session."""

    def __init__(self, base: str, token: str | None = None) -> None:
        self.base = base.rstrip("/")
        self.token = token

    # ── getting in ───────────────────────────────────────────────────────────

    @classmethod
    def sign_in(cls, base: str, email: str, secret: str) -> "Platform":
        open_ = cls(base)
        said = open_.request("POST", "/api/v1/sessions",
                             {"email": email, "secret": secret})
        return cls(base, said["token"])

    @classmethod
    def from_environment(cls) -> "Platform":
        """The session an MCP server starts with.

        Credentials come from the environment and never from a tool argument.
        An agent that can be told a password in a prompt is an agent that can be
        told somebody else's, and the whole point of the grants this platform
        already has is that a session is a person.
        """
        base = os.environ.get("CORAL_CITY_PLATFORM")
        email = os.environ.get("CORAL_CITY_EMAIL")
        secret = os.environ.get("CORAL_CITY_SECRET")
        token = os.environ.get("CORAL_CITY_TOKEN")
        if base is None:
            raise Refused(0, "not_configured",
                          "set CORAL_CITY_PLATFORM to the platform's address")
        if token:
            return cls(base, token)
        if not email or not secret:
            raise Refused(0, "not_configured",
                          "set CORAL_CITY_EMAIL and CORAL_CITY_SECRET, "
                          "or CORAL_CITY_TOKEN")
        return cls.sign_in(base, email, secret)

    # ── asking ───────────────────────────────────────────────────────────────

    def request(self, method: str, path: str, body: Any = None) -> Any:
        headers = {"accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["content-type"] = "application/json"
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        ask = urllib.request.Request(self.base + path, data=data,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(ask, timeout=120) as answer:
                raw = answer.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as problem:
            raw = problem.read()
            try:
                said = json.loads(raw)["error"]
            except Exception:
                said = {"code": "refused", "message": raw.decode()[:400]}
            raise Refused(problem.code, said.get("code", "refused"),
                          said.get("message", "")) from problem

    # ── the routes this server uses, named ───────────────────────────────────

    def me(self) -> dict:
        return self.request("GET", "/api/v1/me")

    def institution(self) -> dict | None:
        said = self.me()
        organisations = said.get("organisations") or []
        return organisations[0] if organisations else None

    def places(self) -> list[dict]:
        return self.request("GET", "/api/v1/cities")["cities"]

    def vehicles(self) -> list[dict]:
        return self.request("GET", "/api/v1/vehicles")["vehicles"]

    def versions_of_place(self, place: str) -> list[dict]:
        return self.request("GET", f"/api/v1/cities/{place}/versions")["versions"]

    def versions_of_vehicle(self, vehicle: str) -> list[dict]:
        return self.request("GET", f"/api/v1/vehicles/{vehicle}/versions")["versions"]

    def files(self, version: str) -> list[dict]:
        return self.request("GET", f"/api/v1/versions/{version}/files")["files"]

    def autonomy(self, organisation: str) -> list[dict]:
        return self.request(
            "GET", f"/api/v1/organisations/{organisation}/autonomy")["autonomy"]

    def dives(self, organisation: str) -> list[dict]:
        return self.request(
            "GET", f"/api/v1/organisations/{organisation}/dives")["dives"]

    def runs(self, dive: str) -> list[dict]:
        return self.request("GET", f"/api/v1/dives/{dive}/runs")["runs"]

    def artefacts(self, dive: str, run: str) -> list[dict]:
        return self.request(
            "GET", f"/api/v1/dives/{dive}/runs/{run}/artefacts")["artefacts"]

    def layouts_of(self, place: str) -> list[dict]:
        return self.request("GET", f"/api/v1/cities/{place}/layouts")["layouts"]

    def missions_of(self, organisation: str) -> list[dict]:
        return self.request(
            "GET", f"/api/v1/organisations/{organisation}/missions")["missions"]

    def queues(self) -> list[dict]:
        return self.request("GET", "/api/v1/queues")["queues"]

    def devices(self) -> list[dict]:
        return self.request("GET", "/api/v1/devices")["devices"]
