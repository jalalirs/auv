#!/usr/bin/env python3
"""Refuse a recursive delete that could take a home directory with it.

Written on 27 September 2026, the night after this command ran on the GPU box:

    ls <a file that was not there> && out=some/path; rm -rf ~/$out

The `ls` failed, so `out` was never set, `~/$out` became `~/`, and every
user-owned file under /home/jalalirs was deleted — ten git checkouts, the
reference corpus, the deployment secrets, and the SSH key that made the box
reachable.

Two rules, and the second is the one that mattered:

  * a recursive delete may not name a home directory, /home, or /;
  * a recursive delete may not name a path built from a shell variable,
    unless the variable carries the `${var:?}` guard that makes an empty
    value abort.

It reads the whole command string, so `ssh host 'rm -rf ~/$x'` is caught the
same as the bare form: the danger is the text, not which binary runs it.
"""

import json
import re
import sys

# A recursive, forceful delete: rm with -r, -R, --recursive, or a bundle
# like -rf / -fr. A plain `rm file` is not this tool's business.
RECURSIVE = re.compile(r"""(?:^|[;&|("\']|\s)  # a boundary, quotes included:
                                                #   ssh host "rm -rf ~/$x" is the same danger
                           (?:sudo\s+)?         # sudo does not make it safer
                           rm\s+
                           (?P<rest>[^;&|)\n]*)  # the rest of this command
                        """, re.VERBOSE)
IS_RECURSIVE = re.compile(r"(?:^|\s)-[a-zA-Z]*[rR]|--recursive")

# Paths that must never be the target of one.
# A home directory, a filesystem root, or one whole tree directly inside a
# home — ~/code and ~/coral-city are entire bodies of work, and nothing
# routine deletes one. Anything deeper is ordinary housekeeping and allowed.
HOME = r"(?:~|\$HOME|\$\{HOME\}|/home/[^/\s]+|/Users/[^/\s]+)"
FORBIDDEN = re.compile(r"^(?:%s/?|/|/home/?|/Users/?|%s/[^/\s]+/?)$"
                       % (HOME, HOME))

# A variable reference that is not guarded by ${name:?...}, which makes the
# shell abort rather than expand an unset name to nothing.
UNGUARDED = re.compile(r"\$(?!\{[A-Za-z_][A-Za-z0-9_]*:\?)[A-Za-z_{]")


def targets(rest: str):
    """The operands of an rm, with its flags dropped."""
    for word in rest.split():
        if word.startswith("-"):
            continue
        yield word.strip("\"'")


def why_not(command: str) -> str | None:
    for match in RECURSIVE.finditer(command):
        rest = match.group("rest")
        if not IS_RECURSIVE.search(" " + rest):
            continue
        for target in targets(rest):
            if FORBIDDEN.match(target):
                return ("refusing `rm -r %s`: that is a home directory or a "
                        "filesystem root." % target)
            if UNGUARDED.search(target):
                return ("refusing `rm -r %s`: the path is built from a shell "
                        "variable. If it is unset the delete lands on the "
                        "parent — which is how /home/jalalirs was destroyed on "
                        "26 September 2026. Write the literal path, or guard "
                        "it as \"${name:?}\" so an empty value aborts."
                        % target)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    reason = why_not(command)
    if reason is None:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "systemMessage": "Blocked a recursive delete: " + reason,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
