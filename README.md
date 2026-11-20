# sidetrack

Linked sub-contexts for [Claude Code](https://code.claude.com).

You're building an app, you need to deploy it, and 40 messages of error logs later Claude has lost the thread of what you built. **sidetrack** lets you branch off into a named context (`deploy`, `brainstorm`, `stripe-bug`), work there, and come back. Lessons are handed to the parent context, and everything important lives in markdown files in your repo, so it survives `/compact`, new sessions, and teammates.

> Status: early development (v0.2.0). The commands work; hooks (automatic context reload and save reminders) come next.

## Commands

| Command | Does |
|---|---|
| `/sidetrack:go <name> [purpose]` | Save the current context, then switch to `<name>` (created as a child of the current one if new) |
| `/sidetrack:back [done]` | Save, hand lessons up to the parent, switch back. `done` marks the finished context as done. |
| `/sidetrack:save` | Checkpoint the current context without switching |
| `/sidetrack:list` | Show the context tree |

Context files live in `.sidetrack/contexts/` and are meant to be committed. `.sidetrack/local/` (your active context) is ignored by git automatically.

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
