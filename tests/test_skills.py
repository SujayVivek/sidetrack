"""Static checks for the skills, plus a dry run of every !`...` injection command.
Run from the repo root: python3 -m unittest discover tests"""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent / "plugins" / "sidetrack"
SKILLS = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
INJECT = re.compile(r"(?:^|(?<=\s))!`([^`]+)`", re.M)


def frontmatter(text):
    lines = text.splitlines()
    assert lines[0].strip() == "---", "missing frontmatter"
    end = lines[1:].index("---") + 1
    meta = {}
    for line in lines[1:end]:
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta, "\n".join(lines[end + 1:])


class SkillTests(unittest.TestCase):
    def test_skills_exist(self):
        self.assertEqual({p.parent.name for p in SKILLS}, {"go", "back", "save", "list"})

    def test_frontmatter(self):
        for p in SKILLS:
            meta, _ = frontmatter(p.read_text())
            self.assertEqual(meta["name"], p.parent.name, p)
            self.assertTrue(meta.get("description"), p)
            self.assertEqual(meta.get("disable-model-invocation"), "true", p)
            self.assertIn("state.py", meta.get("allowed-tools", ""), p)

    def test_no_arguments_inside_shell_injection(self):
        # $ARGUMENTS inside a !`...` command would be shell injection
        for p in SKILLS:
            for cmd in INJECT.findall(p.read_text()):
                self.assertNotIn("$ARGUMENTS", cmd, p)
                self.assertNotIn("$0", cmd, p)

    def test_injection_commands_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, CLAUDE_PROJECT_DIR=tmp)
            for p in SKILLS:
                cmds = INJECT.findall(p.read_text())
                self.assertTrue(cmds, f"{p} has no injected status")
                for cmd in cmds:
                    cmd = cmd.replace("${CLAUDE_SKILL_DIR}", str(p.parent))
                    r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env)
                    self.assertEqual(r.returncode, 0, f"{p}: {cmd}\n{r.stdout}{r.stderr}")
                    self.assertTrue(r.stdout.strip(), f"{p}: empty output for {cmd}")
                    self.assertNotIn("ERROR:", r.stdout, f"{p}: {cmd}")

    def test_referenced_paths_exist(self):
        for p in SKILLS:
            text = p.read_text().replace("${CLAUDE_SKILL_DIR}", str(p.parent))
            for m in re.findall(r'"([^"]*\.(?:py|md))"', text):
                self.assertTrue(Path(os.path.normpath(m)).exists(), f"{p}: {m}")


if __name__ == "__main__":
    unittest.main()
