#!/usr/bin/env python3
"""SessionStart hook: reload the active sidetrack context.

Runs on startup, resume, clear and compact. After a /compact this puts the
saved notes straight back into the conversation, which is what makes
compacting safe. On startup and resume it also reports what teammates
changed since the last session. Silent in projects without .sidetrack/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook_common  # noqa: E402

MAX_CHARS = 6000

INTRO = {
    "startup": "New session.",
    "resume": "Session resumed.",
    "clear": "The conversation was cleared.",
    "compact": "The conversation was just compacted; these saved notes replace what was dropped.",
}

GUIDE = (
    "How sidetrack works: the active context's file is the saved memory for this line of work. "
    "The user controls it with /sidetrack:go <name>, /sidetrack:back, /sidetrack:save and /sidetrack:list. "
    "Do not switch contexts, edit context files or edit .sidetrack/local/state.json on your own; the commands do that. "
    "If the user starts talking about the topic of one of the other contexts, suggest the switch in one line and carry on."
)


def main():
    data = hook_common.read_input()
    import state

    if not state.CONTEXTS.is_dir():
        return
    source = str(data.get("source") or "startup")
    st = state.load_state()
    ctxs = state.all_contexts()
    active = st["active"]
    if active not in ctxs:
        return
    info = ctxs[active]

    parts = [f"[sidetrack] {INTRO.get(source, 'Session started.')}",
             f"Active context: {active}" + (f" - {info['purpose']}" if info["purpose"] else ""),
             "Path: " + " > ".join(reversed(state.chain(active, ctxs))),
             "Other contexts: " + (", ".join(n for n in ctxs if n != active) or "none"),
             f"File: {state.rel(state.ctx_path(active))} (read it for full detail)"]
    conflicted = [n for n in ctxs if state.has_conflict_markers(n)]
    if conflicted:
        parts.append("WARNING: unresolved git conflict markers in context file(s): " + ", ".join(conflicted) +
                     ". Tell the user to run /sidetrack:resolve, and do not write to those files until then.")

    for title, limit in (("Current state", 1500), ("Open threads", 1000)):
        body = state.read_section(active, title, limit)
        parts.append(f"\n### {active}: {title}\n{body or '(nothing saved yet)'}")
    parent = info["parent"]
    if parent in ctxs and parent != active:
        body = state.read_section(parent, "Current state", 800)
        if body:
            parts.append(f"\n### {parent} (parent): Current state\n{body}")

    if source in ("startup", "resume"):
        report = state.changes_since(st.get("last_seen_commit"), state.author())
        if report:
            parts.append("\n### Changes from teammates\n" + report)
        head = state.head_commit()
        if head and head != st.get("last_seen_commit"):
            st["last_seen_commit"] = head
            state.save_state(st)

    parts.append("\n" + GUIDE)
    text = "\n".join(parts)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rstrip() + "\n...(truncated)"
    hook_common.emit("SessionStart", text)


if __name__ == "__main__":
    hook_common.run(main)
