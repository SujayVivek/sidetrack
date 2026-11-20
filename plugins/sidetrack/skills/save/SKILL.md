---
name: save
description: Checkpoint the active sidetrack context to its markdown file without switching contexts.
disable-model-invocation: true
allowed-tools: Bash(python3 *state.py*) Bash(python *state.py*)
---

You are running the sidetrack "save" command.

## Where things stand

!`python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" status 2>&1 || python "${CLAUDE_SKILL_DIR}/../../scripts/state.py" status 2>&1 || echo "ERROR: could not run state.py (is Python 3 installed?)"`

Author name for log entries:

!`python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" author 2>&1 || python "${CLAUDE_SKILL_DIR}/../../scripts/state.py" author 2>&1`

## Rules for writing context files

!`python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" rules 2>&1 || python "${CLAUDE_SKILL_DIR}/../../scripts/state.py" rules 2>&1`

## Steps

1. Read the active context's file (the `file` shown above).
2. Following the rules above, rewrite "Current state" and "Open threads", and append any new decisions and gotchas from this conversation that are not already in the file.
3. Run `python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" saved` (use `python` if `python3` is not found).
4. Reply in one or two lines: the context saved and what changed (for example "2 decisions, 1 gotcha added"). If nothing new needed saving, say so.
