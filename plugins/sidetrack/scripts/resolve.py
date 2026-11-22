#!/usr/bin/env python3
"""sidetrack conflict resolver: the deterministic half of /sidetrack:resolve.

When two people edit the same context file, git leaves conflict markers in it.
This script merges everything that can be merged safely by rules, and leaves
only the judgement call (rewriting the two "state" sections) to Claude.

  resolve.py list              list context files that contain conflict markers
  resolve.py prepare <name>    merge the file by rules and print what Claude must reconcile
  resolve.py verify <name>     check the finished file: no markers, nothing lost
  resolve.py restore <name>    put the original conflicted file back

How the merge works
  frontmatter ........ created=earliest, updated=latest, anything else: ours wins (differences are reported)
  Decisions, Gotchas & fixes, Sent to parent (append-only)
                       every entry from both sides is kept; exact duplicates are dropped;
                       entries are ordered by date
  Current state, Open threads (rewritten sections)
                       if both sides agree the text is kept; otherwise our side is kept and the section
                       is flagged with a pending marker that only a reconciled rewrite removes

The original conflicted file is saved to .sidetrack/local/resolve/<name>.conflicted.md.
Stdlib only, Python 3.8+.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.dont_write_bytecode = True
import state  # noqa: E402

SECTIONS = ["Current state", "Decisions", "Gotchas & fixes", "Open threads", "Sent to parent"]
APPEND = {"Decisions", "Gotchas & fixes", "Sent to parent"}
FM_KEYS = ["name", "parent", "purpose", "status", "created", "updated"]
PENDING = "<!-- sidetrack:resolve-pending -->"

START = re.compile(r"^<{7}(?: .*)?$")
BASE = re.compile(r"^\|{7}(?: .*)?$")
MID = re.compile(r"^={7}$")
END = re.compile(r"^>{7}(?: .*)?$")
ENTRY_DATE = re.compile(r"^- (\d{4}-\d{2}-\d{2})")
HEADER = re.compile(r"^##[ \t]+(.+?)[ \t]*$")
FRONT = re.compile(r"\A---\n(.*?)\n---[ \t]*(?:\n|\Z)(.*)\Z", re.S)


class ConflictError(Exception):
    pass


def backup_path(name: str) -> Path:
    return state.LOCAL / "resolve" / f"{name}.conflicted.md"


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


# ---------- parsing ----------

def split_sides(text: str):
    """Return (ours_text, theirs_text, (our_label, their_label)) from a file with conflict markers."""
    ours, theirs = [], []
    mode = None  # None | "ours" | "base" | "theirs"
    labels = ["ours", "theirs"]
    for line in text.split("\n"):
        if mode is None:
            if START.match(line):
                mode = "ours"
                labels[0] = line[8:].strip() or "ours"
            elif END.match(line):
                raise ConflictError("found '>>>>>>>' without a matching '<<<<<<<'")
            else:
                ours.append(line)
                theirs.append(line)
        elif mode == "ours":
            if BASE.match(line):
                mode = "base"
            elif MID.match(line):
                mode = "theirs"
            elif START.match(line) or END.match(line):
                raise ConflictError("malformed or nested conflict markers")
            else:
                ours.append(line)
        elif mode == "base":
            if MID.match(line):
                mode = "theirs"
            elif START.match(line) or END.match(line):
                raise ConflictError("malformed or nested conflict markers")
        else:  # theirs
            if END.match(line):
                mode = None
                labels[1] = line[8:].strip() or "theirs"
            elif START.match(line) or MID.match(line) or BASE.match(line):
                raise ConflictError("malformed or nested conflict markers")
            else:
                theirs.append(line)
    if mode is not None:
        raise ConflictError("a conflict block is never closed (missing '>>>>>>>')")
    return "\n".join(ours), "\n".join(theirs), tuple(labels)


def parse_doc(text: str):
    """Return (frontmatter dict, {section title: [lines]}, [section titles in file order])."""
    m = FRONT.match(text)
    if not m:
        raise ConflictError("a side of the file has no valid frontmatter")
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    sections, order, cur = {}, [], None
    for line in m.group(2).split("\n"):
        h = HEADER.match(line)
        if h:
            cur = h.group(1)
            if cur not in sections:
                order.append(cur)
                sections[cur] = []
            continue
        if cur is not None:
            sections[cur].append(line)
    for k in sections:
        sections[k] = trim(sections[k])
    return fm, sections, order


def trim(lines):
    lines = list(lines)
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return lines


def norm(lines) -> str:
    return " ".join(" ".join(lines).split()).lower()


def split_entries(lines):
    """Split an append-only section into (header lines, [entry line-lists])."""
    header, entries = [], []
    for ln in lines:
        if ln.startswith("- "):
            entries.append([ln])
        elif entries:
            entries[-1].append(ln)
        else:
            header.append(ln)
    return trim(header), [trim(e) for e in entries]


# ---------- merging ----------

def merge_fm(o: dict, t: dict):
    notes, out = [], {}
    keys = list(FM_KEYS) + [k for k in list(o) + list(t) if k not in FM_KEYS]
    for k in dict.fromkeys(keys):
        a, b = o.get(k), t.get(k)
        if a is None and b is None:
            continue
        if a is None:
            out[k] = b
        elif b is None or a == b:
            out[k] = a
        elif k == "created":
            out[k] = min(a, b)
        elif k == "updated":
            out[k] = max(a, b)
        elif k == "purpose" and not a.strip():
            out[k] = b
        else:
            out[k] = a
            notes.append(f"{k} differs: kept ours ({a}); theirs had ({b})")
    return out, notes


def dated(entries):
    """Pair each entry with a sort date: its own, else the previous entry's, else ''."""
    out, last = [], ""
    for e in entries:
        m = ENTRY_DATE.match(e[0])
        if m:
            last = m.group(1)
        out.append((last, e))
    return out


def merge_append(ours, theirs):
    oh, oe = split_entries(ours)
    th, te = split_entries(theirs)
    seen, merged = set(), []
    stats = {"ours": 0, "theirs": 0, "dup": 0}
    for side, items in (("ours", dated(oe)), ("theirs", dated(te))):
        for d, e in items:
            k = norm(e)
            if k in seen:
                stats["dup"] += 1
                continue
            seen.add(k)
            stats[side] += 1
            merged.append((d, e))
    merged.sort(key=lambda x: x[0])  # stable: ours first on equal dates
    lines = list(oh or th)
    for _, e in merged:
        lines.extend(e)
    return lines, stats


def build(fm: dict, sections: dict, order: list) -> str:
    out = ["---"] + [f"{k}: {v}" for k, v in fm.items()] + ["---", ""]
    for title in order:
        out.append(f"## {title}")
        out.extend(sections[title])
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def do_merge(raw: str):
    ours_t, theirs_t, labels = split_sides(raw)
    ofm, osec, oorder = parse_doc(ours_t)
    tfm, tsec, torder = parse_doc(theirs_t)
    fm, fm_notes = merge_fm(ofm, tfm)
    titles = [t for t in SECTIONS if t in osec or t in tsec]
    titles += [t for t in oorder + torder if t not in titles]
    titles = list(dict.fromkeys(titles))
    merged, report, pending = {}, [], []
    for title in titles:
        a, b = osec.get(title), tsec.get(title)
        if a is None or b is None:
            merged[title] = list(a if a is not None else b)
        elif title in APPEND:
            merged[title], st = merge_append(a, b)
            report.append(f"{title}: {st['ours']} from ours, {st['theirs']} from theirs, {st['dup']} exact duplicate(s) dropped")
        elif norm(a) == norm(b):
            merged[title] = list(a)
        else:
            merged[title] = [PENDING] + list(a)
            pending.append((title, a, b))
    return build(fm, merged, titles), fm_notes, report, pending, labels


# ---------- commands ----------

def need_name(args):
    if not args:
        state.fail("usage: resolve.py <list|prepare|verify|restore> [name]")
    name = args[0].strip().lower()
    if not state.NAME_RE.match(name):
        state.fail(f"invalid context name '{name}'")
    if not state.ctx_path(name).exists():
        state.fail(f"no such context: {name}")
    return name


def cmd_list(_args):
    names = [p.stem for p in sorted(state.CONTEXTS.glob("*.md")) if state.has_conflict_markers(p.stem)] \
        if state.CONTEXTS.is_dir() else []
    print("conflicted: " + ", ".join(names) if names else "none")


def cmd_prepare(args):
    name = need_name(args)
    p = state.ctx_path(name)
    raw = read_text(p)
    if not state.has_conflict_markers(name):
        print(f"nothing to do: '{name}' has no conflict markers")
        return
    try:
        text, fm_notes, report, pending, labels = do_merge(raw)
    except ConflictError as e:
        state.fail(f"cannot merge '{name}' automatically: {e}. The file was not changed; resolve it by hand.")
    state.atomic_write(backup_path(name), raw)
    state.atomic_write(p, text)
    print(f"prepared: {name}")
    print(f"file: {state.rel(p)}")
    print(f"sides: ours = {labels[0]}, theirs = {labels[1]}")
    for line in report:
        print(line)
    for note in fm_notes:
        print(f"frontmatter: {note}")
    if pending:
        print("needs reconciliation: " + ", ".join(t for t, _, _ in pending))
        for title, a, b in pending:
            print(f"\n=== {title}: OURS ({labels[0]}) ===")
            print("\n".join(a[:60]) or "(empty)")
            print(f"\n=== {title}: THEIRS ({labels[1]}) ===")
            print("\n".join(b[:60]) or "(empty)")
    else:
        print("needs reconciliation: nothing (both sides agree on the state sections)")
    print("\nnext: reconcile the sections above in the file, remove each pending marker, then run verify")


def entries_of(fm_text: str, section: str):
    _, sec, _ = parse_doc(fm_text)
    return split_entries(sec.get(section, []))[1]


def cmd_verify(args):
    name = need_name(args)
    p = state.ctx_path(name)
    text = read_text(p)
    problems, warnings = [], []
    if state.has_conflict_markers(name):
        problems.append("conflict markers are still in the file")
    if PENDING in text:
        problems.append("a pending marker is still in the file: a state section has not been reconciled yet")
    sec = {}
    try:
        fm, sec, _ = parse_doc(text)
        for k in FM_KEYS:
            if k not in fm:
                problems.append(f"frontmatter is missing '{k}'")
        for t in SECTIONS:
            if t not in sec:
                problems.append(f"section '## {t}' is missing")
        if len(sec.get("Current state", [])) > 20:
            warnings.append(f"Current state is {len(sec['Current state'])} lines long (the rules say at most 15)")
    except ConflictError as e:
        problems.append(str(e))
    bp = backup_path(name)
    if bp.exists() and sec:
        try:
            ours_t, theirs_t, _ = split_sides(read_text(bp))
            for title in APPEND:
                have = {norm(e) for e in split_entries(sec.get(title, []))[1]}
                for side, t in (("ours", ours_t), ("theirs", theirs_t)):
                    for e in entries_of(t, title):
                        if norm(e) not in have:
                            problems.append(f"an entry from {side} was lost in '{title}': {e[0][:90]}")
        except ConflictError:
            pass
    for w in warnings:
        print(f"warning: {w}")
    if problems:
        for pr in problems:
            print(f"problem: {pr}")
        sys.exit(1)
    state.set_meta(p, "updated", state.today())
    if bp.exists():
        bp.unlink()
    print(f"ok: {name} is resolved. Stage it with: git add {state.rel(p)}")


def cmd_restore(args):
    name = need_name(args)
    bp = backup_path(name)
    if not bp.exists():
        state.fail(f"no saved original for '{name}'")
    state.atomic_write(state.ctx_path(name), read_text(bp))
    print(f"restored: {name} is back to its conflicted original")


COMMANDS = {"list": cmd_list, "prepare": cmd_prepare, "verify": cmd_verify, "restore": cmd_restore}


def main(argv):
    if not argv or argv[0] not in COMMANDS:
        print(__doc__.strip())
        sys.exit(2)
    COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
