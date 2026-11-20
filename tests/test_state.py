"""Tests for scripts/state.py. Run from the repo root: python3 -m unittest discover tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "plugins" / "sidetrack" / "scripts" / "state.py"


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cmd(self, *args, ok=True):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
        r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def kv(self, out):
        return dict(line.split(": ", 1) for line in out.strip().splitlines() if ": " in line)

    def state(self):
        return json.loads((self.root / ".sidetrack/local/state.json").read_text())

    def test_init_creates_layout(self):
        self.run_cmd("init")
        self.assertTrue((self.root / ".sidetrack/contexts/main.md").exists())
        self.assertEqual((self.root / ".sidetrack/.gitignore").read_text().strip().splitlines()[-1], "local/")
        self.assertEqual(self.state()["active"], "main")
        self.assertEqual(self.kv(self.run_cmd("init"))["initialized"], "already")

    def test_go_creates_child_of_active(self):
        out = self.kv(self.run_cmd("go", "deploy", "Get", "it", "live"))
        self.assertEqual(out["created"], "yes")
        self.assertEqual(out["parent"], "main")
        text = (self.root / ".sidetrack/contexts/deploy.md").read_text()
        self.assertIn("parent: main", text)
        self.assertIn("purpose: Get it live", text)
        self.assertEqual(self.state()["active"], "deploy")

    def test_nested_and_back(self):
        self.run_cmd("go", "deploy")
        self.assertEqual(self.kv(self.run_cmd("go", "stripe-bug"))["parent"], "deploy")
        self.assertEqual(self.kv(self.run_cmd("back"))["active"], "deploy")
        self.assertEqual(self.kv(self.run_cmd("back"))["active"], "main")
        r = self.run_cmd("back", ok=False)
        self.assertNotEqual(r, "")
        self.assertIn("root context", r)

    def test_existing_context_keeps_parent(self):
        self.run_cmd("go", "deploy")
        self.run_cmd("back")
        self.run_cmd("go", "brainstorm")
        out = self.kv(self.run_cmd("go", "deploy"))
        self.assertEqual(out["created"], "no")
        self.assertEqual(out["parent"], "main")  # not re-parented under brainstorm

    def test_invalid_name(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
        r = subprocess.run([sys.executable, str(SCRIPT), "go", "../etc"], capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)

    def test_uppercase_is_normalised(self):
        self.assertEqual(self.kv(self.run_cmd("go", "Deploy"))["active"], "deploy")

    def test_corrupted_state_recovers(self):
        self.run_cmd("go", "deploy")
        (self.root / ".sidetrack/local/state.json").write_text("{not json")
        self.assertEqual(self.kv(self.run_cmd("status"))["active"], "main")

    def test_deleted_active_context_recovers(self):
        self.run_cmd("go", "deploy")
        (self.root / ".sidetrack/contexts/deploy.md").unlink()
        self.assertEqual(self.kv(self.run_cmd("status"))["active"], "main")

    def test_tick_and_saved(self):
        self.run_cmd("go", "deploy")
        self.run_cmd("tick")
        self.assertEqual(self.kv(self.run_cmd("tick"))["turns_since_save"], "2")
        self.run_cmd("saved")
        self.assertEqual(self.state()["turns_since_save"], 0)

    def test_list_tree(self):
        self.run_cmd("go", "deploy")
        self.run_cmd("go", "stripe-bug")
        out = self.run_cmd("list")
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("- main"))
        self.assertTrue(lines[1].startswith("  - deploy"))
        self.assertTrue(lines[2].startswith("    - stripe-bug"))
        self.assertIn("<- active", lines[2])

    def test_parent_cycle_does_not_hang(self):
        self.run_cmd("go", "a")
        self.run_cmd("go", "b")
        p = self.root / ".sidetrack/contexts/a.md"
        p.write_text(p.read_text().replace("parent: main", "parent: b"))
        out = self.run_cmd("list")
        self.assertIn("a", out)
        self.assertIn("b", out)
        self.run_cmd("status")


if __name__ == "__main__":
    unittest.main()
