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
    assert "CORAL_CITY_PLATFORM" in said["result"]["content"][0]["text"]


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

    This told every caller to "set CORAL_CITY_PLATFORM and either
    CORAL_CITY_TOKEN or CORAL_CITY_EMAIL/SECRET" whatever had happened —
    including when all three were set and the platform had rejected them, which
    is an instruction to do the thing that was already done.
    """
    rejected = Refused(401, "bad_credentials", "that email and secret do not match")
    said = s.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                     "params": {"name": "places_list"}}, None, rejected)
    body = json.loads(said["result"]["content"][0]["text"])
    assert body["refused"] == "bad_credentials"
    assert "do not match" in body["why"]
    assert "CORAL_CITY_PLATFORM" not in body["why"]


def test_and_an_unset_one_still_says_what_to_set():
    said = s.handle({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                     "params": {"name": "places_list"}}, None, None)
    assert "CORAL_CITY_PLATFORM" in said["result"]["content"][0]["text"]
