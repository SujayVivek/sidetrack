---
name: list
description: Show the tree of sidetrack contexts for this project and which one is active.
disable-model-invocation: true
allowed-tools: Bash(python3 *state.py*) Bash(python *state.py*)
---

Show the user the context tree below exactly as printed, in a code block, followed by one line explaining how to switch (`/sidetrack:go <name>`) or return (`/sidetrack:back`). Add nothing else.

!`python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" list 2>&1 || python "${CLAUDE_SKILL_DIR}/../../scripts/state.py" list 2>&1 || echo "ERROR: could not run state.py (is Python 3 installed?)"`
