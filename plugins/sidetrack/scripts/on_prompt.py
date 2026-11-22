#!/usr/bin/env python3
"""UserPromptSubmit hook: tag every prompt with the active sidetrack context.

Adds one short line to Claude's context, counts the turn, and now and then
suggests saving. Silent in projects without a .sidetrack/ folder.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook_common  # noqa: E402

NUDGE_REPEAT = 10  # after the first reminder, repeat every this many turns


def main():
    data = hook_common.read_input()
    import state

    if not state.CONTEXTS.is_dir():
        return
    prompt = str(data.get("prompt") or "").lstrip()
    if prompt.startswith("/sidetrack"):
        return  # sidetrack commands manage the state themselves
    st = state.load_state()
    is_command = prompt.startswith("/")  # slash commands are not real turns
    if not is_command:
        st["turns_since_save"] += 1

    ctxs = state.all_contexts()
    active = st["active"]
    if active not in ctxs:
        state.save_state(st)
        return
    others = [n for n, i in ctxs.items() if n != active and i["status"] != "done"]
    n = st["turns_since_save"]
    tag = (f"[sidetrack] Active: {active} ({state.rel(state.ctx_path(active))}; parent: {ctxs[active]['parent']}). "
           f"Others: {', '.join(others) or 'none'}. Unsaved turns: {n}.")

    try:
        threshold = max(1, int(os.environ.get("SIDETRACK_NUDGE_TURNS", "15")))
    except ValueError:
        threshold = 15
    # Remind at the first prompt at or past the threshold, then again every NUDGE_REPEAT turns
    # until the user saves (saving or switching context clears nudged_at).
    last = st.get("nudged_at")
    if not is_command and n >= threshold and (last is None or n - last >= NUDGE_REPEAT):
        st["nudged_at"] = n
        tag += (f" ACTION REQUIRED: after you finish answering, end your reply with exactly this one line: "
                f"\"sidetrack: {n} turns since the last save. Run /sidetrack:save to checkpoint.\" "
                "Do not edit the context file yourself.")
    state.save_state(st)
    if state.has_conflict_markers(active):
        tag += (f" WARNING: {state.rel(state.ctx_path(active))} has unresolved git conflict markers. "
                "Tell the user to run /sidetrack:resolve, and do not write to the file until it is resolved.")
    hook_common.emit("UserPromptSubmit", tag)


if __name__ == "__main__":
    hook_common.run(main)
