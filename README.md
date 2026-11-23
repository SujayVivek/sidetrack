# sidetrack

**Side quests for Claude Code, without losing the main story.**

You are building an app. Then you need to deploy it. Forty messages of error logs later, Claude has lost the thread of what you built.

sidetrack lets you step aside into a named context (`deploy`, `stripe-bug`, `brainstorm`), work there, and come back. What matters is saved in small markdown files in your repo, so it survives `/compact`, new sessions and teammates.

> Status: beta (v0.5.0). Commands, hooks and merge-conflict resolution work. Feedback and issues are welcome.

## How it works

```
main ──── go deploy ────▶ deploy ──── back ────▶ main
 │                          │                      │
 │  Current state           │  Decisions           │  lessons from deploy
 │  Decisions               │  Gotchas & fixes     │  are waiting here
 └─ .sidetrack/contexts/main.md   └─ .sidetrack/contexts/deploy.md
```

- A **context** is a named piece of work. Contexts form a tree: `deploy` is a child of `main`.
- Each context has a **context file** in `.sidetrack/contexts/`. You commit it with your code.
- When you switch, the context you leave is saved and the new one is loaded.
- When you go back, lessons are handed up to the parent.

## Quick start

```
/plugin marketplace add SujayVivek/sidetrack
/plugin install sidetrack@sidetrack
```

Then, in any project:

```
/sidetrack:go deploy getting it live     # create "deploy" and switch to it
...fix things, break things...
/sidetrack:back done                     # save, hand lessons up, return to main
```

Requires Python 3 (`python3`, or `python` on Windows). No other dependencies.

## Commands

| Command | What it does |
|---|---|
| `/sidetrack:go <name> [purpose]` | Save the current context, then switch to `<name>`. A new name is created as a child of the current context. |
| `/sidetrack:back [done]` | Save, hand lessons up to the parent, switch back. `done` marks the finished context as done. |
| `/sidetrack:save` | Save the current context without switching. |
| `/sidetrack:list` | Show the context tree. Contexts with a merge conflict are flagged. |
| `/sidetrack:resolve` | Fix a git merge conflict in context files. |

Names use lowercase letters, digits and dashes, up to 40 characters.

## What a context file holds

| Section | How it changes |
|---|---|
| Current state | Rewritten on each save (15 lines at most) |
| Decisions | Only added to |
| Gotchas & fixes | Only added to |
| Sent to parent | Only added to |
| Open threads | Rewritten on each save |

Added lines look like `- 2026-11-20 (author): text`. Only the commands above write context files. The hooks never do.

## Hooks (automatic)

- **Every message** gets a one-line tag for Claude: the active context, its parent, the other contexts and the number of unsaved turns.
- **Save reminder.** After 15 unsaved turns, Claude ends its reply with a one-line reminder to run `/sidetrack:save`. It repeats every 10 turns. Change the threshold with `SIDETRACK_NUDGE_TURNS`.
- **On startup, resume, `/clear` and `/compact`**, the active context's "Current state" and "Open threads" (and its parent's state) are put back into the conversation. This is what makes `/compact` safe.
- **On startup and resume**, you get a short report of commits and context changes made by teammates since your last session.
- In projects without a `.sidetrack/` folder, the hooks do nothing.

## Working in a team

Context files go to git, so a teammate who pulls your work gets your context too. Your active context is not shared: it lives in `.sidetrack/local/`, which git ignores.

When a merge leaves conflict markers in a context file, run `/sidetrack:resolve`:

1. A script merges by rule. Every decision, gotcha and "sent to parent" line from both sides is kept, exact duplicates are dropped, and lines are ordered by date. The original is saved in `.sidetrack/local/resolve/`.
2. Claude writes one "Current state" and one "Open threads" that are true for both sides, and flags any contradiction for you to decide.
3. A second script checks that no line from either side was lost.

It never runs git commands. You stage the file and finish the merge yourself.

## Troubleshooting

- **Claude does not seem to see the tag or the reloaded context.** Set `SIDETRACK_HOOK_OUTPUT=plain` to switch the hooks to plain-text output.
- **Something broke in a hook.** Hooks never block your work. Errors go to `.sidetrack/local/hook-error.log`.
- **Two Claude windows on one project** share the same active context.

Never put secrets in context files. They are committed to git.

## Develop locally

```
git clone https://github.com/SujayVivek/sidetrack
cd sidetrack
claude --plugin-dir ./plugins/sidetrack
python3 -m unittest discover tests
```

## License

MIT
