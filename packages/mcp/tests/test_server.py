"""The protocol, spoken to without a client library.

Three methods and no framework, so the test drives it the same way an assistant
does: JSON-RPC lines in, JSON-RPC lines out.
"""

from __future__ import annotations

import json

from coral_city_mcp import server as s
from coral_city_mcp.platform import Refused


def test_it_introduces_itself_with_the_rule():
    """The instructions have to say what {value, kind, from} means, because an
    agent that does not know will report a derived figure as a measurement."""
    said = s.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, None)
    told = said["result"]["instructions"]
    for word in ("measured", "derived", "chosen", "assumed"):
        assert word in told
    assert said["result"]["capabilities"]["tools"] == {}


def test_every_tool_says_what_it_takes():
    said = s.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, None)
    tools = said["result"]["tools"]
    assert len(tools) >= 6
    for one in tools:
        assert one["description"].strip()
        assert one["inputSchema"]["type"] == "object"
        for needed in one["inputSchema"].get("required", []):
            assert needed in one["inputSchema"]["properties"], one["name"]


def test_an_unknown_tool_is_a_protocol_error():
    said = s.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "drop_tables"}}, None)
    assert said["error"]["code"] == -32601


def test_calling_without_a_session_says_what_to_set():
    said = s.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                     "params": {"name": "places_list"}}, None)
    assert said["result"]["isError"] is True
    assert "IOCEAN_PLATFORM" in said["result"]["content"][0]["text"]


def test_a_refusal_comes_back_as_content_not_as_a_crash():
    """A refusal is the platform working correctly. An agent should read the
    reason and ask for something else, not treat it as the server falling
    over."""
    class Says:
        def places(self):
            raise Refused(403, "not_granted", "nobody has granted you a place")

    said = s.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                     "params": {"name": "places_list"}}, Says())
    body = json.loads(said["result"]["content"][0]["text"])
    assert body["refused"] == "not_granted"
    assert "granted" in body["why"]


def test_initialized_is_a_notification_and_gets_no_reply():
    assert s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, None) is None


def test_a_rejected_credential_is_not_reported_as_an_unset_one():
    """Two different problems with two different fixes.

    This told every caller to "set IOCEAN_PLATFORM and either
    IOCEAN_TOKEN or IOCEAN_EMAIL/SECRET" whatever had happened —
    including when all three were set and the platform had rejected them, which
    is an instruction to do the thing that was already done.
    """
    rejected = Refused(401, "bad_credentials", "that email and secret do not match")
    said = s.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                     "params": {"name": "places_list"}}, None, rejected)
    body = json.loads(said["result"]["content"][0]["text"])
    assert body["refused"] == "bad_credentials"
    assert "do not match" in body["why"]
    assert "IOCEAN_PLATFORM" not in body["why"]


def test_and_an_unset_one_still_says_what_to_set():
    said = s.handle({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                     "params": {"name": "places_list"}}, None, None)
    assert "IOCEAN_PLATFORM" in said["result"]["content"][0]["text"]


# ── over HTTP ────────────────────────────────────────────────────────────────

def _serve():
    import socket
    import threading

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    threading.Thread(target=s.serve_http, args=("127.0.0.1", port), daemon=True).start()
    import time
    time.sleep(0.3)
    return f"http://127.0.0.1:{port}"


def _post(base, body, auth=None):
    import urllib.request
    headers = {"content-type": "application/json"}
    if auth:
        headers["authorization"] = auth
    ask = urllib.request.Request(base + "/mcp", data=json.dumps(body).encode(),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(ask, timeout=10) as answer:
        raw = answer.read()
        return answer.status, (json.loads(raw) if raw else None)


def test_it_lists_its_tools_over_http():
    base = _serve()
    status, said = _post(base, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert status == 200
    assert len(said["result"]["tools"]) >= 15


def test_a_notification_gets_202_and_no_body():
    base = _serve()
    status, said = _post(base, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert status == 202 and said is None


def test_without_a_credential_it_says_how_to_get_one():
    """The server holds none of its own. Each agent brings its own."""
    base = _serve()
    _, said = _post(base, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                           "params": {"name": "places_list"}})
    body = json.loads(said["result"]["content"][0]["text"])
    assert body["refused"] == "unauthenticated"
    assert "Tokens for your assistant" in body["why"]


def test_the_caller_s_credential_is_the_one_used():
    """Every agent acts as the principal it was issued as. A shared credential
    in a server reachable from the whole tailnet would make every agent the
    same agent."""
    platform, why = s._platform_for("Service prin_7:secret")
    assert why is None and platform.service == "prin_7:secret"
    platform, why = s._platform_for("Bearer tok")
    assert why is None and platform.token == "tok"
    platform, why = s._platform_for("Basic Zm9v")
    assert platform is None and why.code == "unauthenticated"


def test_health_answers_for_the_compose_check():
    import urllib.request
    base = _serve()
    with urllib.request.urlopen(base + "/health", timeout=10) as answer:
        assert json.loads(answer.read())["ok"] is True
