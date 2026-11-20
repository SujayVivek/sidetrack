"""Shared plumbing for the sidetrack hooks.

Rules every hook follows:
  * never crash Claude Code: any error is swallowed and the hook exits 0
  * never create files in a project that does not use sidetrack
  * print nothing when there is nothing to say
"""
import json
import os
import sys
import traceback
from pathlib import Path

sys.dont_write_bytecode = True  # do not litter the plugin folder with __pycache__


def read_input() -> dict:
    """Read the hook's JSON from stdin. Call this BEFORE importing state, because it may chdir."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    cwd = data.get("cwd")
    if isinstance(cwd, str) and cwd and not os.environ.get("CLAUDE_PROJECT_DIR") and os.path.isdir(cwd):
        os.chdir(cwd)
    return data


def emit(event: str, text: str) -> None:
    """Add `text` to Claude's context. SIDETRACK_HOOK_OUTPUT=plain switches to plain stdout."""
    if not text:
        return
    if os.environ.get("SIDETRACK_HOOK_OUTPUT", "").lower() == "plain":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        print(text)
    else:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))


def run(main) -> None:
    try:
        main()
    except BaseException:  # noqa: BLE001 - a hook must never break the session
        try:
            base = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()) / ".sidetrack" / "local"
            if base.is_dir():
                (base / "hook-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
    sys.exit(0)
