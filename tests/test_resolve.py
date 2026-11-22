"""Tests for scripts/resolve.py, using REAL git merge conflicts. Run: python3 -m unittest discover tests"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "sidetrack" / "scripts"
RESOLVE = SCRIPTS / "resolve.py"
STATE = SCRIPTS / "state.py"
_boot = tempfile.mkdtemp()
os.environ.setdefault("CLAUDE_PROJECT_DIR", _boot)
sys.path.insert(0, str(SCRIPTS))
import resolve as R  # noqa: E402

BASE = """---
name: deploy
parent: main
purpose: Get it live
status: open
created: 2026-11-18
updated: 2026-11-19
---

## Current state
Base state.

## Decisions
<!-- Append only. -->
- 2026-11-18 (me): use Railway

## Gotchas & fixes
<!-- Append only. -->

## Open threads
- base thread

## Sent to parent
<!-- Append only. -->
"""


def edit(text, **sections):
    """Replace section bodies in a context file text."""
    for title, body in sections.items():
        title = title.replace("_", " ")
        text = re.sub(rf"(## {re.escape(title)}\n)(.*?)(?=\n## |\Z)", lambda m: m.group(1) + body + "\n", text, flags=re.S)
    return text


OURS = edit(BASE,
            Current_state="Ours: app builds, Dockerfile written.",
            Decisions="<!-- Append only. -->\n- 2026-11-18 (me): use Railway\n- 2026-11-20 (sujay): use gunicorn\n- 2026-11-21 (sujay): port comes from PORT env var")
OURS = OURS.replace("## Gotchas & fixes\n<!-- Append only. -->\n", "## Gotchas & fixes\n<!-- Append only. -->\n- 2026-11-20 (sujay): 502 until PORT is read from env\n")
OURS = OURS.replace("updated: 2026-11-19", "updated: 2026-11-21").replace("- base thread", "- write Dockerfile healthcheck")
THEIRS = edit(BASE,
              Current_state="Theirs: switched to Postgres, migrations done.",
              Decisions="<!-- Append only. -->\n- 2026-11-18 (me): use Railway\n- 2026-11-19 (rahul): use Postgres not SQLite\n- 2026-11-21 (sujay): port comes from PORT env var")
THEIRS = THEIRS.replace("## Gotchas & fixes\n<!-- Append only. -->\n", "## Gotchas & fixes\n<!-- Append only. -->\n- 2026-11-22 (rahul): Postgres URL must use the private network host\n")
THEIRS = THEIRS.replace("updated: 2026-11-19", "updated: 2026-11-22").replace("- base thread", "- run migrations on deploy")


class GitConflictCase(unittest.TestCase):
    style = "merge"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *a, check=True):
        r = subprocess.run(["git", "-c", "user.name=Me", "-c", "user.email=m@x.com",
                            "-c", f"merge.conflictstyle={self.style}", *a],
                           capture_output=True, text=True, cwd=str(self.root))
        if check:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def run_cmd(self, script, *args, ok=True):
        r = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True,
                           env=self.env, cwd=str(self.root))
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def make_conflict(self, ours=OURS, theirs=THEIRS):
        self.git("init", "-q")
        self.git("checkout", "-q", "-b", "main")
        self.run_cmd(STATE, "go", "deploy")
        self.f = self.root / ".sidetrack/contexts/deploy.md"
        self.f.write_text(BASE)
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.git("checkout", "-q", "-b", "rahul")
        self.f.write_text(theirs)
        self.git("commit", "-qam", "rahul's work")
        self.git("checkout", "-q", "main")
        self.f.write_text(ours)
        self.git("commit", "-qam", "sujay's work")
        r = self.git("merge", "rahul", check=False)
        self.assertNotEqual(r.returncode, 0, "expected a merge conflict")
        self.assertRegex(self.f.read_text(), r"(?m)^<<<<<<< ")

    def section(self, text, title):
        m = re.search(rf"## {re.escape(title)}\n(.*?)(?=\n## |\Z)", text, re.S)
        return m.group(1) if m else None

    def reconcile(self):
        text = self.f.read_text()
        text = edit(text, Current_state="Merged: app builds with Postgres; Dockerfile written.",
                    Open_threads="- write Dockerfile healthcheck\n- run migrations on deploy")
        self.f.write_text(text)

    # ----- the tests -----

    def test_list(self):
        self.make_conflict()
        self.assertEqual(self.run_cmd(RESOLVE, "list").stdout.strip(), "conflicted: deploy")

    def test_prepare_merges_by_rules(self):
        self.make_conflict()
        out = self.run_cmd(RESOLVE, "prepare", "deploy").stdout
        text = self.f.read_text()
        self.assertNotRegex(text, r"(?m)^(<{7}|>{7})")
        # every entry from both sides is present exactly once
        for entry in ("use Railway", "use gunicorn", "use Postgres not SQLite", "port comes from PORT env var",
                      "502 until PORT is read from env", "private network host"):
            self.assertEqual(text.count(entry), 1, entry)
        # ordered by date
        d = self.section(text, "Decisions")
        self.assertLess(d.index("2026-11-18"), d.index("2026-11-19"))
        self.assertLess(d.index("2026-11-19"), d.index("2026-11-20"))
        self.assertLess(d.index("2026-11-20"), d.index("2026-11-21"))
        # frontmatter: latest updated, earliest created
        self.assertIn("updated: 2026-11-22", text)
        self.assertIn("created: 2026-11-18", text)
        # both rewritten sections are pending, and Claude is shown both versions
        self.assertEqual(text.count(R.PENDING), 2)
        self.assertIn("=== Current state: OURS", out)
        self.assertIn("Ours: app builds", out)
        self.assertIn("=== Current state: THEIRS", out)
        self.assertIn("Theirs: switched to Postgres", out)
        self.assertIn("=== Open threads: THEIRS", out)
        self.assertIn("2 exact duplicate(s) dropped", out)  # the shared base entry and the line both people added
        self.assertTrue((self.root / ".sidetrack/local/resolve/deploy.conflicted.md").exists())

    def test_verify_fails_until_reconciled_then_passes(self):
        self.make_conflict()
        self.run_cmd(RESOLVE, "prepare", "deploy")
        r = self.run_cmd(RESOLVE, "verify", "deploy", ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("pending marker", r.stdout)
        self.reconcile()
        r = self.run_cmd(RESOLVE, "verify", "deploy")
        self.assertIn("ok: deploy is resolved", r.stdout)
        self.assertIn("git add .sidetrack/contexts/deploy.md", r.stdout)
        self.assertIn(f"updated: {date.today().isoformat()}", self.f.read_text())
        self.assertFalse((self.root / ".sidetrack/local/resolve/deploy.conflicted.md").exists())
        # the finished file can be committed to complete the merge
        self.git("add", ".")
        self.git("commit", "-qm", "merge rahul")
        self.assertEqual(self.run_cmd(RESOLVE, "list").stdout.strip(), "none")

    def test_verify_catches_a_lost_entry(self):
        self.make_conflict()
        self.run_cmd(RESOLVE, "prepare", "deploy")
        self.reconcile()
        text = self.f.read_text().replace("- 2026-11-19 (rahul): use Postgres not SQLite\n", "")
        self.f.write_text(text)
        r = self.run_cmd(RESOLVE, "verify", "deploy", ok=False)
        self.assertIn("an entry from theirs was lost in 'Decisions'", r.stdout)
        self.assertIn("use Postgres", r.stdout)

    def test_verify_catches_leftover_markers_and_missing_sections(self):
        self.make_conflict()
        r = self.run_cmd(RESOLVE, "verify", "deploy", ok=False)  # never prepared
        self.assertIn("conflict markers are still in the file", r.stdout)
        self.run_cmd(RESOLVE, "prepare", "deploy")
        self.reconcile()
        self.f.write_text(self.f.read_text().replace("## Open threads", "## Open stuff"))
        r = self.run_cmd(RESOLVE, "verify", "deploy", ok=False)
        self.assertIn("section '## Open threads' is missing", r.stdout)

    def test_restore(self):
        self.make_conflict()
        original = self.f.read_text()
        self.run_cmd(RESOLVE, "prepare", "deploy")
        self.assertNotEqual(self.f.read_text(), original)
        self.run_cmd(RESOLVE, "restore", "deploy")
        self.assertEqual(self.f.read_text(), original)

    def test_prepare_without_conflict_is_a_noop(self):
        self.run_cmd(STATE, "go", "deploy")
        before = (self.root / ".sidetrack/contexts/deploy.md").read_text()
        out = self.run_cmd(RESOLVE, "prepare", "deploy").stdout
        self.assertIn("nothing to do", out)
        self.assertEqual((self.root / ".sidetrack/contexts/deploy.md").read_text(), before)

    def test_agreeing_state_sections_need_no_reconciliation(self):
        ours = edit(BASE, Decisions="<!-- Append only. -->\n- 2026-11-18 (me): use Railway\n- 2026-11-20 (sujay): a")
        theirs = edit(BASE, Decisions="<!-- Append only. -->\n- 2026-11-18 (me): use Railway\n- 2026-11-20 (rahul): b")
        self.make_conflict(ours, theirs)
        out = self.run_cmd(RESOLVE, "prepare", "deploy").stdout
        self.assertIn("nothing (both sides agree", out)
        self.assertNotIn(R.PENDING, self.f.read_text())
        self.assertIn("ok:", self.run_cmd(RESOLVE, "verify", "deploy").stdout)
        text = self.f.read_text()
        self.assertIn("(sujay): a", text)
        self.assertIn("(rahul): b", text)

    def test_section_only_one_side_added_is_kept(self):
        theirs = THEIRS + "\n## Links\n- https://railway.app/docs\n"
        self.make_conflict(OURS, theirs)
        self.run_cmd(RESOLVE, "prepare", "deploy")
        self.assertIn("## Links", self.f.read_text())
        self.assertIn("railway.app/docs", self.f.read_text())

    def test_frontmatter_differences_are_reported(self):
        ours = OURS.replace("purpose: Get it live", "purpose: Get it live on Railway")
        theirs = THEIRS.replace("purpose: Get it live", "purpose: Ship to prod").replace("status: open", "status: done")
        self.make_conflict(ours, theirs)
        out = self.run_cmd(RESOLVE, "prepare", "deploy").stdout
        self.assertIn("purpose differs: kept ours", out)
        self.assertIn("status differs: kept ours", out)
        self.assertIn("purpose: Get it live on Railway", self.f.read_text())

    def test_crlf_files(self):
        self.make_conflict()
        self.f.write_bytes(self.f.read_text().replace("\n", "\r\n").encode())
        self.run_cmd(RESOLVE, "prepare", "deploy")
        self.assertNotRegex(self.f.read_text(), r"(?m)^(<{7}|>{7})")
        self.assertEqual(self.f.read_text().count("use gunicorn"), 1)


class Diff3Style(GitConflictCase):
    style = "diff3"  # markers include a '|||||||' base section; every test above runs again


class MarkerParsing(unittest.TestCase):
    def test_setext_underline_outside_a_conflict_is_plain_text(self):
        ours, theirs, _ = R.split_sides("Title\n=======\nbody")
        self.assertEqual(ours, "Title\n=======\nbody")
        self.assertEqual(theirs, ours)

    def test_sides_and_labels(self):
        ours, theirs, labels = R.split_sides("a\n<<<<<<< HEAD\nO\n=======\nT\n>>>>>>> origin/main\nz")
        self.assertEqual(ours, "a\nO\nz")
        self.assertEqual(theirs, "a\nT\nz")
        self.assertEqual(labels, ("HEAD", "origin/main"))

    def test_diff3_base_is_ignored(self):
        ours, theirs, _ = R.split_sides("<<<<<<< HEAD\nO\n||||||| base\nB\n=======\nT\n>>>>>>> x")
        self.assertEqual((ours, theirs), ("O", "T"))

    def test_malformed_markers_raise(self):
        for bad in ("<<<<<<< HEAD\nO\n=======\nT", "x\n>>>>>>> y", "<<<<<<< a\n<<<<<<< b\n=======\n>>>>>>> c"):
            with self.assertRaises(R.ConflictError):
                R.split_sides(bad)

    def test_malformed_file_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, CLAUDE_PROJECT_DIR=d)
            subprocess.run([sys.executable, str(STATE), "go", "deploy"], env=env, capture_output=True, cwd=d)
            f = Path(d) / ".sidetrack/contexts/deploy.md"
            broken = BASE + "\n<<<<<<< HEAD\nonly one side, never closed\n"
            f.write_text(broken)
            r = subprocess.run([sys.executable, str(RESOLVE), "prepare", "deploy"], env=env, capture_output=True, text=True, cwd=d)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("error:", r.stdout)
            self.assertIn("resolve it by hand", r.stdout)
            self.assertEqual(f.read_text(), broken)


class ListShowsConflicts(unittest.TestCase):
    def test_list_marks_conflicted_context(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, CLAUDE_PROJECT_DIR=d)
            subprocess.run([sys.executable, str(STATE), "go", "deploy"], env=env, capture_output=True, cwd=d)
            f = Path(d) / ".sidetrack/contexts/deploy.md"
            f.write_text(f.read_text() + "\n<<<<<<< HEAD\nA\n=======\nB\n>>>>>>> x\n")
            out = subprocess.run([sys.executable, str(STATE), "list"], env=env, capture_output=True, text=True, cwd=d).stdout
            self.assertIn("[CONFLICT: run /sidetrack:resolve]", out)
            self.assertNotIn("main [open, updated " + "x", out)


if __name__ == "__main__":
    unittest.main()
