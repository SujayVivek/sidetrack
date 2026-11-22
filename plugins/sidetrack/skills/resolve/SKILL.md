---
name: resolve
description: Resolve git merge conflicts in sidetrack context files. Merges decisions and gotchas from both sides, then reconciles the state sections.
disable-model-invocation: true
allowed-tools: Bash(python3 *resolve.py*) Bash(python *resolve.py*)
---

You are running the sidetrack "resolve" command. It fixes context files that git left with conflict markers after a merge, pull or rebase.

## Conflicted context files

!`python3 "${CLAUDE_SKILL_DIR}/../../scripts/resolve.py" list 2>&1 || python "${CLAUDE_SKILL_DIR}/../../scripts/resolve.py" list 2>&1 || echo "ERROR: could not run resolve.py (is Python 3 installed?)"`

## Steps

If the list above says `none`, tell the user no context files have conflicts, and that if git reports conflicts elsewhere those files are not sidetrack's. Stop.

Otherwise, for each conflicted context, one at a time:

1. **Prepare.** Run `python3 "${CLAUDE_SKILL_DIR}/../../scripts/resolve.py" prepare <name>` (use `python` if `python3` is not found). The script merges the file by rules: every decision, gotcha and "sent to parent" entry from both sides is kept, exact duplicates are dropped, and entries are ordered by date. It saves the original conflicted file for safety. If it prints `error:`, show it to the user, leave that file alone, and move on to the next one.
2. **Reconcile the pending sections.** The script prints the two versions of each section it could not merge (usually "Current state" and "Open threads") and leaves our side in the file under a `<!-- sidetrack:resolve-pending -->` marker. Read both versions, then edit the file so each pending section holds ONE reconciled text:
   - Current state: at most 15 lines, describing what is true now after both people's work. Keep facts from both sides. If the sides disagree about a fact, do not pick silently: state both and flag it in Open threads.
   - Open threads: the union of unfinished work and questions from both sides. Drop an item only if the other side's text shows it is done.
   - If an entry in Decisions or Gotchas contradicts another (for example two different choices for the same thing), do not delete either. Add a line to Open threads: "Conflict: <A> vs <B>: decide."
   - Remove each `<!-- sidetrack:resolve-pending -->` marker when you rewrite its section.
   - Do not touch the frontmatter, and do not remove or reword any entry in Decisions, Gotchas & fixes or Sent to parent.
3. **Verify.** Run `... resolve.py verify <name>`. If it prints `problem:` lines, fix exactly those and run it again. After two failed attempts, run `... resolve.py restore <name>`, and tell the user the file needs resolving by hand.
4. **Report** in at most 6 lines: for each context resolved, how many entries came from each side, any contradictions you flagged, and any frontmatter differences the script reported. Finish with: "Review the files, then stage them: `git add .sidetrack/contexts/<name>.md`, and continue your merge or rebase (`git merge --continue`, `git rebase --continue`, or `git commit`). I have not run any git commands."

Never run git commands yourself. Never put secrets in a context file.
