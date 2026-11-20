#!/usr/bin/env python3
"""sidetrack state manager.

Handles everything deterministic: folders, context files, the active
context, the parent tree and the save counter. Claude never edits
state.json by hand; it calls this script.

Usage:
  state.py init                  create .sidetrack/ and the root context "main"
  state.py go <name> [purpose]   switch to <name>, creating it (child of the active context) if new
  state.py back                  switch to the active context's parent
  state.py list                  print the context tree
  state.py status                print the active context and save counter
  state.py saved                 record a save: reset counter, bump 'updated' date
  state.py tick                  count one user turn (used by the prompt hook)
  state.py author                print the author name used in log entries

Project root: $CLAUDE_PROJECT_DIR, else the git top level, else the cwd.
Stdlib only, Python 3.8+.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT_CONTEXT = "main"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "context.md"


# ---------- paths ----------

def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.cwd()


ROOT = project_root()
BASE = ROOT / ".sidetrack"
CONTEXTS = BASE / "contexts"
LOCAL = BASE / "local"
STATE = LOCAL / "state.json"


def ctx_path(name: str) -> Path:
    return CONTEXTS / f"{name}.md"


def rel(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


# ---------- io helpers ----------

def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def today() -> str:
    return date.today().isoformat()


def fail(msg: str, code: int = 1):
    print(f"error: {msg}")
    sys.exit(code)


# ---------- frontmatter ----------

def read_meta(path: Path) -> dict:
    """Parse simple 'key: value' frontmatter between the first two '---' lines."""
    meta = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return meta
    if not lines or lines[0].strip() != "---":
        return meta
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def set_meta(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    parts = text.split("\n---", 1)  # [frontmatter-with-opening, rest]
    if not text.startswith("---") or len(parts) < 2:
        return
    head, rest = parts
    pattern = re.compile(rf"^{re.escape(key)}:.*$", re.M)
    if pattern.search(head):
        head = pattern.sub(f"{key}: {value}", head, count=1)
    else:
        head = head + f"\n{key}: {value}"
    atomic_write(path, head + "\n---" + rest)


# ---------- state ----------

def default_state() -> dict:
    return {"active": ROOT_CONTEXT, "turns_since_save": 0, "last_seen_commit": None}


def load_state() -> dict:
    st = default_state()
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            st.update(data)
    except (OSError, ValueError):
        pass  # missing or corrupted: fall back to defaults
    # active context must exist on disk; otherwise recover to main
    if not NAME_RE.match(str(st.get("active", ""))) or not ctx_path(st["active"]).exists():
        st["active"] = ROOT_CONTEXT
    if not isinstance(st.get("turns_since_save"), int):
        st["turns_since_save"] = 0
    return st


def save_state(st: dict) -> None:
    atomic_write(STATE, json.dumps(st, indent=2) + "\n")


# ---------- setup ----------

def author() -> str:
    try:
        out = subprocess.run(["git", "config", "user.name"], capture_output=True,
                             text=True, timeout=5, cwd=str(ROOT))
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


def new_context(name: str, parent: str, purpose: str) -> Path:
    tpl = TEMPLATE.read_text(encoding="utf-8")
    text = (tpl.replace("{{name}}", name)
               .replace("{{parent}}", parent)
               .replace("{{purpose}}", purpose or "(not set)")
               .replace("{{date}}", today()))
    p = ctx_path(name)
    atomic_write(p, text)
    return p


def ensure_init() -> bool:
    """Create the folder layout and root context if missing. Returns True if anything was created."""
    created = False
    CONTEXTS.mkdir(parents=True, exist_ok=True)
    LOCAL.mkdir(parents=True, exist_ok=True)
    gi = BASE / ".gitignore"
    if not gi.exists():
        atomic_write(gi, "# per-user state, never commit\nlocal/\n")
        created = True
    if not ctx_path(ROOT_CONTEXT).exists():
        new_context(ROOT_CONTEXT, "none", "Root context: the main line of work on this project")
        created = True
    if not STATE.exists():
        save_state(default_state())
        created = True
    return created


# ---------- tree ----------

def all_contexts() -> dict:
    out = {}
    if CONTEXTS.exists():
        for p in sorted(CONTEXTS.glob("*.md")):
            meta = read_meta(p)
            name = meta.get("name") or p.stem
            out[p.stem] = {"parent": meta.get("parent", "none"),
                           "purpose": meta.get("purpose", ""),
                           "status": meta.get("status", ""),
                           "updated": meta.get("updated", ""),
                           "declared_name": name}
    return out


def chain(name: str, ctxs: dict) -> list:
    """Ancestors from name up to the root, stopping on cycles or missing parents."""
    seen, out = set(), []
    cur = name
    while cur in ctxs and cur not in seen:
        seen.add(cur)
        out.append(cur)
        cur = ctxs[cur]["parent"]
    return out


# ---------- commands ----------

def print_kv(**kv):
    for k, v in kv.items():
        print(f"{k}: {v}")


def cmd_init(_args):
    created = ensure_init()
    st = load_state()
    print_kv(initialized="yes" if created else "already",
             active=st["active"], file=rel(ctx_path(st["active"])))


def cmd_go(args):
    if not args:
        fail("usage: go <name> [purpose]")
    name = args[0].strip().lower()
    purpose = " ".join(args[1:]).strip()
    if not NAME_RE.match(name):
        fail(f"invalid name '{name}': use lowercase letters, digits and dashes (max 40 chars)")
    ensure_init()
    st = load_state()
    prev = st["active"]
    if name == prev:
        print_kv(switched="no", reason="already active", active=name, file=rel(ctx_path(name)))
        return
    created = not ctx_path(name).exists()
    if created:
        new_context(name, prev, purpose)
    elif purpose:
        set_meta(ctx_path(name), "purpose", purpose)
    set_meta(ctx_path(name), "status", "active")
    st["active"] = name
    st["turns_since_save"] = 0
    save_state(st)
    meta = read_meta(ctx_path(name))
    print_kv(switched="yes", previous=prev, previous_file=rel(ctx_path(prev)),
             active=name, file=rel(ctx_path(name)), created="yes" if created else "no",
             parent=meta.get("parent", "none"),
             parent_file=rel(ctx_path(meta["parent"])) if meta.get("parent", "none") != "none" else "none")


def cmd_back(_args):
    ensure_init()
    st = load_state()
    cur = st["active"]
    parent = read_meta(ctx_path(cur)).get("parent", "none")
    if cur == ROOT_CONTEXT or parent in ("none", ""):
        fail(f"'{cur}' is the root context; there is nothing to go back to")
    if not ctx_path(parent).exists():
        fail(f"parent '{parent}' of '{cur}' does not exist")
    st["active"] = parent
    st["turns_since_save"] = 0
    save_state(st)
    print_kv(switched="yes", previous=cur, previous_file=rel(ctx_path(cur)),
             active=parent, file=rel(ctx_path(parent)))


def cmd_list(_args):
    ensure_init()
    st = load_state()
    ctxs = all_contexts()
    children = {}
    for n, info in ctxs.items():
        children.setdefault(info["parent"], []).append(n)
    printed = set()

    def walk(n, depth):
        if n in printed:
            return
        printed.add(n)
        info = ctxs[n]
        mark = "  <- active" if n == st["active"] else ""
        purpose = f" | {info['purpose']}" if info["purpose"] else ""
        print(f"{'  ' * depth}- {n} [{info['status'] or '?'}, updated {info['updated'] or '?'}]{purpose}{mark}")
        for c in sorted(children.get(n, [])):
            walk(c, depth + 1)

    roots = [n for n, i in ctxs.items() if i["parent"] in ("none", "") or i["parent"] not in ctxs]
    for r in sorted(roots, key=lambda x: (x != ROOT_CONTEXT, x)):
        walk(r, 0)
    for n in sorted(set(ctxs) - printed):  # anything in a parent cycle
        walk(n, 0)


def cmd_status(_args):
    ensure_init()
    st = load_state()
    ctxs = all_contexts()
    print_kv(active=st["active"], file=rel(ctx_path(st["active"])),
             path=" > ".join(reversed(chain(st["active"], ctxs))),
             turns_since_save=st["turns_since_save"],
             others=", ".join(n for n in ctxs if n != st["active"]) or "none")


def cmd_saved(_args):
    ensure_init()
    st = load_state()
    st["turns_since_save"] = 0
    save_state(st)
    set_meta(ctx_path(st["active"]), "updated", today())
    print_kv(saved=st["active"], file=rel(ctx_path(st["active"])), updated=today())


def cmd_tick(_args):
    ensure_init()
    st = load_state()
    st["turns_since_save"] += 1
    save_state(st)
    print_kv(active=st["active"], turns_since_save=st["turns_since_save"])


def cmd_author(_args):
    print(author())


COMMANDS = {"init": cmd_init, "go": cmd_go, "back": cmd_back, "list": cmd_list,
            "status": cmd_status, "saved": cmd_saved, "tick": cmd_tick, "author": cmd_author}


def main(argv):
    if not argv or argv[0] not in COMMANDS:
        print(__doc__.strip())
        sys.exit(2)
    COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    main(sys.argv[1:])
