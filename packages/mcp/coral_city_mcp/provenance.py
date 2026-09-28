"""Every value an agent is handed, with where it came from attached.

Named `provenance` rather than `said` because the package exports the
function `said` from it, and a module and a function of one name means the
package's own __init__ shadows one with the other — which it did, and the
first thing that noticed was `from coral_city_mcp import said` returning a
function where a module was wanted. The platform already calls this
provenance everywhere else; so does this.

This is the whole reason a customer should point their assistant at us rather
than at a simulator they wrote themselves. An assistant asked for a number will
produce one; the risk of putting one between an operator and a decision is that
nothing in the loop knows which numbers were measured. This platform has spent
its whole life refusing to state a figure without its source — `provenance.json`
ships with every deliverable, a fitted seabed says it is derived and says the
depth it holds to, a bench row that cannot name its water says so.

Carried into MCP that becomes a property of the transport: a tool here does not
return `19.11`. It returns 19.11 marked *derived*, from the Allen Coral Atlas,
and an agent that reports it as a measurement is contradicting its own input.

The four words are the platform's own, used unchanged:

  measured   somebody put an instrument on it
  derived    computed from something measured, and the computation is named
  chosen     a person picked it, and it could have been picked differently
  assumed    nobody picked it; it is a default nobody has revisited
"""

from __future__ import annotations

from typing import Any

MEASURED = "measured"
DERIVED = "derived"
CHOSEN = "chosen"
ASSUMED = "assumed"

KINDS = (MEASURED, DERIVED, CHOSEN, ASSUMED)


def said(value: Any, kind: str, source: str, note: str | None = None) -> dict:
    """One value, its kind, and who to blame for it.

    `source` is not optional and not allowed to be empty. A value marked
    measured with nothing naming the instrument is exactly the laundered
    measurement this platform exists to refuse, and it is easier to refuse it
    here than to find it later in somebody's report.
    """
    if kind not in KINDS:
        raise ValueError(f"{kind!r} is not one of {KINDS}")
    if not source or not source.strip():
        raise ValueError(
            f"a {kind} value needs a source: {value!r} came from somewhere")
    out = {"value": value, "kind": kind, "from": source.strip()}
    if note:
        out["note"] = note
    return out


def unknown(why: str) -> dict:
    """Nobody recorded it.

    Distinct from a value of zero and from null, and it is worth a word of its
    own because those two are what an agent will otherwise infer. A bench row
    written before the water was a field did not fly in still water; nobody
    wrote down what it flew in.
    """
    return {"value": None, "kind": None, "from": None, "unknown": why}


def numbers(of: dict) -> list[str]:
    """Which keys of a returned object are bare numbers.

    Used by the tests rather than the server: the rule is that a tool's answer
    carries no naked figure anywhere in it, and a rule of that shape is only
    worth having if something checks the whole tree.
    """
    found: list[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if "kind" in node and "from" in node:
                return              # a said() value: its number is accounted for
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for at, value in enumerate(node):
                walk(value, f"{path}[{at}]")
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            found.append(path)

    walk(of, "")
    return found
