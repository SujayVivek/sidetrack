# How to write sidetrack context files

Context files live in `.sidetrack/contexts/<name>.md` and are committed to git, so teammates and future sessions read them. Treat them as shared project notes, not a chat log.

## File layout
Each file has frontmatter (name, parent, purpose, status, created, updated) followed by five sections. Never edit the frontmatter yourself: `state.py` owns it.

| Section | How to update |
|---|---|
| Current state | REWRITE completely at every save. Max 15 lines. What is true right now: what exists, what works, what is broken, where we stopped. |
| Decisions | APPEND only. One line each. |
| Gotchas & fixes | APPEND only. One line each, as "problem → fix". |
| Open threads | REWRITE at every save. Unfinished work and open questions. |
| Sent to parent | APPEND only. Log of lessons handed to the parent. |

## Line format for the append-only sections
`- YYYY-MM-DD (author): text`
- The date is today's date. The author is the name from `state.py author`.
- One self-contained line, under about 200 characters, understandable without the chat.
- Read the file first. Do not add a line that is already there, and do not add a line that contradicts an earlier one without saying it replaces it.

## What to record
- Decisions and the reason for them ("use Celery for the scheduler: needs retries").
- Constraints and facts the next session needs: file paths, command names, config and env var NAMES, versions, service names, URLs of docs.
- Gotchas: the error or trap, and the fix that worked.
- Where work stopped and what comes next.

## What never goes in
- Secrets: API keys, tokens, passwords, connection strings, env var VALUES. Write the variable name only. These files are committed to GitHub.
- Logs, stack traces, long command output, or the back-and-forth of debugging. Keep only the conclusion.
- Anything obvious from the code or git history.
- Guesses stated as facts. If unsure, say so in the line.

## Merging up to the parent (used by /sidetrack:back)
Pick 0 to 5 lessons from the child that change what the parent should do or know: a decision that affects the app, a config requirement, a constraint, a gotcha the parent will also hit.
- Append each to the parent's "Decisions" or "Gotchas & fixes" section, tagged: `- YYYY-MM-DD (author): text (from <child>)`.
- Append a one-line record of each to the child's "Sent to parent" section.
- If nothing affects the parent, send nothing and say so. Do not pad.
- If the parent's "Current state" is now wrong because of a lesson, correct that line.

## Safety checks
- If a context file contains git conflict markers (<<<<<<<, =======, >>>>>>>), stop and tell the user. Do not write to it.
- If a file is over about 300 lines, condense the oldest log entries into a few summary lines when you next save it.
