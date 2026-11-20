---
name: back
description: Save the active sidetrack context, hand its lessons up to the parent context, and switch back to the parent. Add "done" to mark the finished context as done.
argument-hint: [done]
disable-model-invocation: true
allowed-tools: Bash(python3 *state.py*) Bash(python *state.py*)
---

You are running the sidetrack "back" command. Follow the steps in order.

User arguments: `$ARGUMENTS`

## Where things stand

!`python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" status 2>&1 || python "${CLAUDE_SKILL_DIR}/../../scripts/state.py" status 2>&1 || echo "ERROR: could not run state.py (is Python 3 installed?)"`

Author name for log entries:

!`python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" author 2>&1 || python "${CLAUDE_SKILL_DIR}/../../scripts/state.py" author 2>&1`

## Rules for writing context files

!`python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" rules 2>&1 || python "${CLAUDE_SKILL_DIR}/../../scripts/state.py" rules 2>&1`

## Steps

1. **Root check.** If the active context is `main` (or the status shows no parent in its path), say there is nothing to go back to and stop.
2. **Save the active context.** Read its file. Following the rules above, rewrite "Current state" and "Open threads" and append new decisions and gotchas. Then run `saved`.
3. **Hand lessons up.** Read the parent's file. Choose 0 to 5 lessons that change what the parent should do or know, following the "Merging up to the parent" rules. Append them to the parent, log them under the child's "Sent to parent", and fix the parent's "Current state" if a lesson makes it wrong.
4. **Switch.** Run `back`. If the arguments contain the word `done`, run `back --done` instead so the context you leave is marked finished. If the script prints `error:`, show it and stop.
5. **Load the parent.** Read the parent's file so you know where that work stands.
6. **Report in at most 6 lines:** the context you left, the lessons sent up (one short line each, or "none"), the context you are in now and its current state in one or two lines. End with: "Run /compact to clear the noise from this chat. Your notes are saved in the files."

## Running the script

Use Bash: `python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" <command> [args]`. If `python3` is not found, use `python`. Never edit `.sidetrack/local/state.json` by hand.
