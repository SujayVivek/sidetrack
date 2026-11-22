"""Tests for the hooks. Run from the repo root: python3 -m unittest discover tests"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "sidetrack"
STATE = PLUGIN / "scripts" / "state.py"
ON_PROMPT = PLUGIN / "scripts" / "on_prompt.py"
ON_START = PLUGIN / "scripts" / "on_session_start.py"


class HookBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.extra_env = {}

    def tearDown(self):
        self.tmp.cleanup()

    def env(self):
        e = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
        e.pop("SIDETRACK_HOOK_OUTPUT", None)
        e.pop("SIDETRACK_NUDGE_TURNS", None)
        e.update(self.extra_env)
        return e

    def state(self, *args):
        r = subprocess.run([sys.executable, str(STATE), *args], capture_output=True, text=True,
                           env=self.env(), cwd=str(self.root))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def hook(self, script, payload, raw=None):
        stdin = raw if raw is not None else json.dumps(payload)
        r = subprocess.run([sys.executable, str(script)], input=stdin, capture_output=True, text=True,
                           env=self.env(), cwd=str(self.root))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # hooks must always exit 0
        return r.stdout

    def context_of(self, out):
        """Extract additionalContext text from a hook's JSON output ('' if no output)."""
        if not out.strip():
            return ""
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]

    def prompt(self, text="hello"):
        return self.context_of(self.hook(ON_PROMPT, {"hook_event_name": "UserPromptSubmit", "prompt": text, "cwd": str(self.root)}))

    def start(self, source="startup"):
        return self.context_of(self.hook(ON_START, {"hook_event_name": "SessionStart", "source": source, "cwd": str(self.root)}))

    def write_ctx(self, name, section, body):
        p = self.root / ".sidetrack/contexts" / f"{name}.md"
        text = p.read_text()
        text = re.sub(rf"(## {re.escape(section)}\n)(.*?)(?=\n## |\Z)", lambda m: m.group(1) + body + "\n", text, flags=re.S)
        p.write_text(text)

    def turns(self):
        return json.loads((self.root / ".sidetrack/local/state.json").read_text())["turns_since_save"]


class HooksNeverTouchContextFiles(HookBase):
    def test_context_files_unchanged_by_hooks(self):
        # Only /sidetrack:go, back and save may change a context file. Hooks only touch local/state.json.
        import hashlib
        self.state("go", "deploy", "Get", "it", "live")
        self.write_ctx("deploy", "Current state", "Railway project created.")
        self.extra_env["SIDETRACK_NUDGE_TURNS"] = "2"

        def snapshot():
            return {p.name: (hashlib.md5(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                    for p in (self.root / ".sidetrack/contexts").glob("*.md")}
        before = snapshot()
        for i in range(6):
            self.prompt(f"message {i}")
        for src in ("startup", "resume", "clear", "compact"):
            self.start(src)
        self.assertEqual(snapshot(), before)
        self.assertEqual(self.turns(), 6)  # ...while state.json did change, as designed


class NoopOutsideSidetrackProjects(HookBase):
    def test_silent_and_creates_nothing(self):
        self.assertEqual(self.hook(ON_PROMPT, {"prompt": "hi"}), "")
        self.assertEqual(self.hook(ON_START, {"source": "startup"}), "")
        self.assertFalse((self.root / ".sidetrack").exists())


class PromptHook(HookBase):
    def test_tag_and_tick(self):
        self.state("go", "deploy", "Get", "it", "live")
        self.state("go", "brainstorm")
        self.state("go", "deploy")
        tag = self.prompt()
        self.assertIn("Active: deploy", tag)
        self.assertIn("parent: main", tag)
        self.assertIn("Others: brainstorm, main", tag)
        self.assertIn("Unsaved turns: 1", tag)
        self.assertIn("Unsaved turns: 2", self.prompt())
        self.assertEqual(self.turns(), 2)

    def test_sidetrack_commands_are_ignored(self):
        self.state("go", "deploy")
        self.assertEqual(self.prompt("/sidetrack:back"), "")
        self.assertEqual(self.turns(), 0)

    def test_other_slash_commands_tag_but_do_not_tick(self):
        self.state("go", "deploy")
        self.assertIn("Active: deploy", self.prompt("/compact"))
        self.assertEqual(self.turns(), 0)

    def test_done_contexts_not_listed_as_others(self):
        self.state("go", "deploy")
        self.state("back", "--done")
        self.state("go", "brainstorm")
        self.assertNotIn("deploy", self.prompt().split("Others:")[1])

    def test_nudge_at_threshold_then_every_ten(self):
        self.state("go", "deploy")
        self.extra_env["SIDETRACK_NUDGE_TURNS"] = "3"
        tags = [self.prompt() for _ in range(13)]
        nudged = [i + 1 for i, t in enumerate(tags) if "/sidetrack:save" in t]
        self.assertEqual(nudged, [3, 13])
        self.assertTrue(all("end your reply with exactly this one line" in tags[i - 1] for i in nudged))
        self.assertIn("sidetrack: 3 turns since the last save", tags[2])
        self.assertTrue(all("Do not edit the context file" in tags[i - 1] for i in nudged))

    def read_state(self):
        return json.loads((self.root / ".sidetrack/local/state.json").read_text())

    def write_state(self, **kw):
        st = self.read_state()
        st.update(kw)
        (self.root / ".sidetrack/local/state.json").write_text(json.dumps(st))

    def test_nudge_fires_when_counter_is_already_past_threshold(self):
        # regression: counter at 3, threshold 1 -> next prompt must nudge, then stay quiet
        self.state("go", "deploy")
        self.write_state(turns_since_save=3)
        self.extra_env["SIDETRACK_NUDGE_TURNS"] = "1"
        first, second, third = self.prompt(), self.prompt(), self.prompt()
        self.assertIn("ACTION REQUIRED", first)
        self.assertIn("4 turns since the last save", first)
        self.assertNotIn("ACTION REQUIRED", second)
        self.assertNotIn("ACTION REQUIRED", third)
        self.assertEqual(self.read_state()["nudged_at"], 4)

    def test_save_and_switch_reset_the_nudge(self):
        self.state("go", "deploy")
        self.extra_env["SIDETRACK_NUDGE_TURNS"] = "2"
        self.prompt(); self.assertIn("ACTION REQUIRED", self.prompt())
        self.state("saved")
        self.assertIsNone(self.read_state()["nudged_at"])
        self.assertEqual(self.read_state()["turns_since_save"], 0)
        self.assertNotIn("ACTION REQUIRED", self.prompt())
        self.assertIn("ACTION REQUIRED", self.prompt())  # fires again after saving and reaching the threshold
        self.state("back")
        self.assertIsNone(self.read_state()["nudged_at"])

    def test_slash_commands_never_nudge(self):
        self.state("go", "deploy")
        self.write_state(turns_since_save=20)
        self.extra_env["SIDETRACK_NUDGE_TURNS"] = "3"
        self.assertNotIn("ACTION REQUIRED", self.prompt("/compact"))
        self.assertIn("ACTION REQUIRED", self.prompt("a real question"))

    def test_old_state_file_without_nudged_at_still_works(self):
        self.state("go", "deploy")
        (self.root / ".sidetrack/local/state.json").write_text(json.dumps({"active": "deploy", "turns_since_save": 0}))
        self.assertIn("Active: deploy", self.prompt())

    def test_bad_threshold_env_falls_back(self):
        self.state("go", "deploy")
        self.extra_env["SIDETRACK_NUDGE_TURNS"] = "banana"
        self.assertIn("Active: deploy", self.prompt())

    def test_conflict_marker_warning(self):
        self.state("go", "deploy")
        p = self.root / ".sidetrack/contexts/deploy.md"
        p.write_text(p.read_text() + "\n<<<<<<< HEAD\nA\n=======\nB\n>>>>>>> other\n")
        out = self.prompt()
        self.assertIn("conflict markers", out)
        self.assertIn("/sidetrack:resolve", out)

    def test_plain_output_mode(self):
        self.state("go", "deploy")
        self.extra_env["SIDETRACK_HOOK_OUTPUT"] = "plain"
        out = self.hook(ON_PROMPT, {"prompt": "hi"})
        self.assertTrue(out.startswith("[sidetrack] Active: deploy"))
        with self.assertRaises(ValueError):
            json.loads(out)

    def test_survives_garbage(self):
        self.state("go", "deploy")
        self.hook(ON_PROMPT, None, raw="this is not json")
        self.hook(ON_PROMPT, None, raw="")
        self.hook(ON_PROMPT, None, raw="[1,2,3]")

    def test_survives_corrupted_state(self):
        self.state("go", "deploy")
        (self.root / ".sidetrack/local/state.json").write_text("{broken")
        self.assertIn("Active: main", self.prompt())


class SessionStartHook(HookBase):
    def test_reloads_saved_state_after_compact(self):
        self.state("go", "deploy", "Get", "it", "live")
        self.write_ctx("main", "Current state", "Social OS works locally; scheduler uses APScheduler.")
        self.write_ctx("deploy", "Current state", "Railway project created; 502 until PORT is read from env.")
        self.write_ctx("deploy", "Open threads", "- add healthcheck endpoint")
        out = self.start("compact")
        self.assertIn("just compacted", out)
        self.assertIn("Active context: deploy - Get it live", out)
        self.assertIn("Path: main > deploy", out)
        self.assertIn("502 until PORT", out)
        self.assertIn("healthcheck", out)
        self.assertIn("### main (parent): Current state", out)
        self.assertIn("APScheduler", out)
        self.assertIn("/sidetrack:go", out)
        self.assertNotIn("<!--", out)  # template placeholders stripped

    def test_empty_sections_say_so(self):
        self.state("go", "deploy")
        self.assertIn("(nothing saved yet)", self.start("clear"))

    def test_oversized_section_is_truncated(self):
        self.state("go", "deploy")
        self.write_ctx("deploy", "Current state", "x" * 5000)
        out = self.start("startup")
        self.assertIn("truncated", out)
        self.assertLess(len(out), 6100)

    def test_all_sources_work(self):
        self.state("go", "deploy")
        for src in ("startup", "resume", "clear", "compact", "something-new"):
            self.assertIn("Active context: deploy", self.start(src))

    def test_survives_garbage_and_corruption(self):
        self.state("go", "deploy")
        self.hook(ON_START, None, raw="nonsense")
        (self.root / ".sidetrack/local/state.json").write_text("")
        self.assertIn("Active context: main", self.start("startup"))

    def test_conflicts_in_any_context_are_announced(self):
        self.state("go", "deploy")
        self.state("go", "brainstorm")
        p = self.root / ".sidetrack/contexts/deploy.md"
        p.write_text(p.read_text() + "\n<<<<<<< HEAD\nA\n=======\nB\n>>>>>>> other\n")
        out = self.start("startup")  # active context is brainstorm, the conflict is in deploy
        self.assertIn("conflict markers in context file(s): deploy", out)
        self.assertIn("/sidetrack:resolve", out)

    def test_missing_contexts_does_not_crash(self):
        self.state("go", "deploy")
        for f in (self.root / ".sidetrack/contexts").glob("*.md"):
            f.unlink()
        self.assertEqual(self.start("startup"), "")


class TeammateReport(HookBase):
    def git(self, *args, user="Me"):
        r = subprocess.run(["git", "-c", f"user.name={user}", "-c", f"user.email={user.lower()}@x.com", *args],
                           capture_output=True, text=True, cwd=str(self.root))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_report_lists_teammate_changes_once(self):
        self.git("init", "-q")
        subprocess.run(["git", "config", "user.name", "Me"], cwd=str(self.root))
        (self.root / "app.py").write_text("print(1)\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.state("go", "deploy")
        self.git("add", ".")
        self.git("commit", "-qm", "add sidetrack contexts")
        first = self.start("startup")
        self.assertNotIn("Changes from teammates", first)  # nothing to compare yet
        self.assertIsNotNone(json.loads((self.root / ".sidetrack/local/state.json").read_text())["last_seen_commit"])

        self.write_ctx("deploy", "Gotchas & fixes", "- 2026-11-21 (Rahul): Railway needs PORT from env")
        (self.root / "app.py").write_text("print(2)\n")
        self.git("add", ".")
        self.git("commit", "-qm", "Move scheduler to Celery", user="Rahul")
        (self.root / "app.py").write_text("print(3)\n")
        self.git("add", ".")
        self.git("commit", "-qm", "my own change")

        report = self.start("resume")
        self.assertIn("Changes from teammates", report)
        self.assertIn("1 commit(s) by others", report)
        self.assertIn("Rahul: Move scheduler to Celery", report)
        self.assertIn("context 'deploy' was updated by Rahul", report)
        self.assertNotIn("my own change", report)
        self.assertNotIn("Changes from teammates", self.start("startup"))  # reported only once
        self.assertNotIn("Changes from teammates", self.start("compact"))  # never on compact

    def test_unknown_last_commit_is_silent(self):
        self.git("init", "-q")
        (self.root / "a").write_text("a")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")
        self.state("go", "deploy")
        st = json.loads((self.root / ".sidetrack/local/state.json").read_text())
        st["last_seen_commit"] = "deadbeef" * 5  # e.g. history was rewritten
        (self.root / ".sidetrack/local/state.json").write_text(json.dumps(st))
        out = self.start("startup")
        self.assertIn("Active context: deploy", out)
        self.assertNotIn("Changes from teammates", out)

    def test_works_outside_git(self):
        self.state("go", "deploy")
        self.assertIn("Active context: deploy", self.start("startup"))


class HooksJson(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())

    def test_wrapper_format_and_events(self):
        self.assertIn("hooks", self.cfg)
        self.assertEqual(set(self.cfg["hooks"]), {"SessionStart", "UserPromptSubmit"})
        self.assertEqual(self.cfg["hooks"]["SessionStart"][0]["matcher"], "startup|resume|clear|compact")

    def test_commands_point_at_real_scripts_with_fallback(self):
        for event, groups in self.cfg["hooks"].items():
            for g in groups:
                for h in g["hooks"]:
                    self.assertEqual(h["type"], "command")
                    self.assertGreater(h["timeout"], 0)
                    cmd = h["command"]
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}", cmd)
                    self.assertIn("python3", cmd)
                    self.assertIn("|| python ", cmd)
                    script = re.search(r"scripts/(\w+\.py)", cmd).group(1)
                    self.assertTrue((PLUGIN / "scripts" / script).exists(), script)


if __name__ == "__main__":
    unittest.main()
