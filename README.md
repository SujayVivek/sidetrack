# sidetrack

Linked sub-contexts for [Claude Code](https://code.claude.com).

You're building an app, you need to deploy it, and 40 messages of error logs later Claude has lost the thread of what you built. **sidetrack** lets you branch off into a named context (`deploy`, `brainstorm`, `stripe-bug`), work there, and come back. Lessons are handed to the parent context, and everything important lives in markdown files in your repo, so it survives `/compact`, new sessions, and teammates.

> Status: early development (v0.1.0). Not ready for use yet.

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
