---
name: go
description: Save the active sidetrack context, then switch to another one (creating it as a child if it is new). Use to branch off into deploy, debug, brainstorm and so on.
argument-hint: <context-name> [purpose]
disable-model-invocation: true
allowed-tools: Bash(python3 *state.py*) Bash(python *state.py*)
---

You are running the sidetrack "go" command. Follow the steps in order.

User arguments: `$ARGUMENTS`

## Where things stand

!`python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" status 2>&1 || python "${CLAUDE_SKILL_DIR}/../../scripts/state.py" status 2>&1 || echo "ERROR: could not run state.py (is Python 3 installed?)"`

Author name for log entries:

!`python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" author 2>&1 || python "${CLAUDE_SKILL_DIR}/../../scripts/state.py" author 2>&1`

## Rules for writing context files

!`python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" rules 2>&1 || python "${CLAUDE_SKILL_DIR}/../../scripts/state.py" rules 2>&1`

## Steps

1. **Read the arguments.** The first word is the target context name. Everything after it is the purpose. If there are no arguments, run `list` (see "Running the script" below), show the tree, ask which context to go to, and stop.
2. **Already there?** If the target is the active context shown above, say so in one line and stop.
3. **Save the context you are leaving.** Read its file (the path is shown above as `file`). Following the rules above, rewrite "Current state" and "Open threads", and append any new decisions and gotchas from this conversation to the append-only sections. Then run `saved`.
4. **Switch.** Run `go <name> <purpose>`. Pass the name as one argument and the purpose as one quoted argument. The script prints the new active context, its file and its parent.
5. **Load the new context.** Read the new context's file. If you just created it, also read its parent's file and write a 2-4 line "Current state" for the new context: its purpose, and the facts from the parent that matter for this work. If it already existed, do not change it yet.
6. **Report in at most 5 lines:** the context you left, the one you are in now (and its parent), whether it is new, and its current state in one or two lines. Nothing else.

From now on, until the user switches again, treat the new context's file as the place to record decisions and gotchas for this work.

## Running the script

Use Bash: `python3 "${CLAUDE_SKILL_DIR}/../../scripts/state.py" <command> [args]`. If `python3` is not found, use `python`. Always quote the purpose. Never edit `.sidetrack/local/state.json` by hand. If the script prints a line starting with `error:`, show it to the user and stop without switching.
