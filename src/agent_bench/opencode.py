"""Run a private OpenCode client and export authoritative per-message measurements.

The adapter embeds this standalone program in the container command, so it must
use only the standard library, not imports from the host's benchmark runner.
"""

import json
from pathlib import Path
import subprocess
import sys


def run_script() -> str:
    """Return the same program exercised by the wrapper's subprocess tests."""

    return Path(__file__).read_text(encoding="utf-8")


def main() -> int:
    workspace, *arguments = sys.argv[1:]
    process = subprocess.Popen(
        ["opencode", "run", *arguments],
        cwd=workspace,
        stdout=subprocess.PIPE,
        text=True,
    )
    session_ids = set()
    terminated = True
    for line in process.stdout:
        print(line, end="", flush=True)
        terminated = line.endswith("\n")
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        session_id = event.get("sessionID") if isinstance(event, dict) else None
        if isinstance(session_id, str) and session_id:
            session_ids.add(session_id)
    process.stdout.close()
    returncode = process.wait()
    if len(session_ids) != 1:
        print("OpenCode did not report exactly one run session", file=sys.stderr)
        return returncode or 1
    session_id = session_ids.pop()
    exported = subprocess.run(
        ["opencode", "session", "export", "--standalone", session_id],
        cwd=workspace,
        stdout=subprocess.PIPE,
        text=True,
    )
    if exported.returncode:
        print("OpenCode session export failed", file=sys.stderr)
        return returncode or exported.returncode
    try:
        session = json.loads(exported.stdout)
        if session["info"]["id"] != session_id or not isinstance(session["messages"], list):
            raise ValueError
        messages = [
            message for message in session["messages"]
            if isinstance(message, dict) and message.get("type") == "assistant"
        ]
        if not messages:
            raise ValueError
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        print("OpenCode returned an invalid session export", file=sys.stderr)
        return returncode or 1
    # Session aggregates can include auxiliary work and replay the same tokens.
    # Publish assistant records once, leaving unrelated tool-result metadata out.
    if not terminated:
        print(flush=True)
    for message in messages:
        print(json.dumps({"type": "bench_opencode_message", "message": message}), flush=True)
    print(json.dumps({"type": "bench_opencode_end", "outcome": session["info"].get("outcome")}), flush=True)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
