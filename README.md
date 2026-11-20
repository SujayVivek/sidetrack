# sidetrack

Linked sub-contexts for [Claude Code](https://code.claude.com).

You're building an app, you need to deploy it, and 40 messages of error logs later Claude has lost the thread of what you built. **sidetrack** lets you branch off into a named context (`deploy`, `brainstorm`, `stripe-bug`), work there, and come back. Lessons are handed to the parent context, and everything important lives in markdown files in your repo, so it survives `/compact`, new sessions, and teammates.

> Status: early development (v0.3.2). Commands and hooks work; `/sidetrack:resolve` for merge conflicts is planned.

## Commands

| Command | Does |
|---|---|
| `/sidetrack:go <name> [purpose]` | Save the current context, then switch to `<name>` (created as a child of the current one if new) |
| `/sidetrack:back [done]` | Save, hand lessons up to the parent, switch back. `done` marks the finished context as done. |
| `/sidetrack:save` | Checkpoint the current context without switching |
| `/sidetrack:list` | Show the context tree |

Context files live in `.sidetrack/contexts/` and are meant to be committed. `.sidetrack/local/` (your active context) is ignored by git automatically.

## Hooks (automatic)

- **Every prompt** gets a one-line tag for Claude: the active context, its parent, the other contexts, and the number of unsaved turns. After 15 unsaved turns Claude ends its reply with a one-line reminder to run `/sidetrack:save` (it repeats every 10 turns). Change the threshold with the environment variable `SIDETRACK_NUDGE_TURNS`.
- **On startup, resume, `/clear` and `/compact`** the active context's saved "Current state" and "Open threads" (and its parent's state) are put back into the conversation. This is what makes `/compact` safe.
- **On startup and resume** you also get a short report of commits and context changes made by teammates since your last session.
- In projects without a `.sidetrack/` folder the hooks do nothing.

Troubleshooting: if Claude does not seem to see the tag or the reloaded context, set `SIDETRACK_HOOK_OUTPUT=plain` in your environment to switch the hooks to plain-text output. Hook errors are written to `.sidetrack/local/hook-error.log`.

Requires Python 3 (`python3`, or `python` on Windows). Never put secrets in context files.

## Install

```
/plugin marketplace add <github-user>/sidetrack
/plugin install sidetrack@sidetrack
```

## Develop locally

```
git clone https://github.com/<github-user>/sidetrack
cd sidetrack
claude --plugin-dir ./plugins/sidetrack
```

## License

MIT
