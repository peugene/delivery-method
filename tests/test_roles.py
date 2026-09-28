"""Role files: who may write a verdict, which commands the prefix rules miss, what the runner and
the lead may reach; and the grace a starting interactive session gets before it counts as dead."""

import importlib
import re
from datetime import datetime, timedelta, timezone
from unittest import mock

from support import RepoCase, write

from deliveryctl import config, roles
from deliveryctl.window import mentions


def denied(perms: dict, command: str) -> bool:
    """Whether a Bash command matches a deny rule, '*' matching anything."""
    for rule in perms["permissions"]["deny"]:
        match = re.fullmatch(r"Bash\((.*)\)", rule)
        if match and re.fullmatch(".*".join(map(re.escape, match.group(1).split("*"))), command):
            return True
    return False


class RolesTest(RepoCase):
    def setUp(self):
        super().setUp()
        write(self.repo / "delivery.toml", 'repo_role = "impl"\nforge = "none"\n[commands]\ncheck = "true"\n')
        self.cfg = config.load(self.repo)
        self.wt = self.tmp / "todo-wt" / "s001"

    def perms(self, role: str) -> dict:
        return roles.permissions(self.cfg, role, self.wt, "s001")

    def test_verdict_files_have_one_author(self):
        wt = "/" + str(self.wt.resolve())
        impl, rev = self.perms("story-implementer")["permissions"], self.perms("story-reviewer")["permissions"]
        for name in ("verification.md", "review.md"):
            self.assertIn(f"Write({wt}/docs/stories/*/{name})", impl["deny"])
            self.assertIn(f"Edit({wt}/docs/stories/*/{name})", impl["deny"])
        self.assertIn(f"Write({wt}/docs/stories/*/verification.md)", rev["deny"])
        self.assertNotIn(f"Write({wt}/docs/stories/*/review.md)", rev["deny"])
        self.assertTrue(denied(self.perms("story-implementer"), "git mv docs/stories/s001/x.md docs/stories/s001/review.md"))
        self.assertTrue(denied(self.perms("story-implementer"), "git mv tmp/verification.md docs/stories/s001/"))
        self.assertFalse(denied(self.perms("story-implementer"), "git mv src/a.py src/b.py"))
        self.assertTrue(denied(self.perms("story-reviewer"), "git mv x docs/stories/s001/verification.md"))

    def test_options_the_prefix_rules_miss(self):
        perms = self.perms("technical-lead")
        for command in ('git commit --allow-empty -m "t" --amend', 'git commit --allow-empty -nm "t"',
                        "git commit -n --allow-empty", "sort -o src/x.txt a.txt", "sort -u a.txt -o src/x",
                        "git diff --output=src/d.txt HEAD~1", "git push --force", "git checkout -f main"):
            self.assertTrue(denied(perms, command), command)
        for command in ('git commit --allow-empty --no-edit -m "ok"', "sort a.txt", "git diff HEAD~1 --stat",
                        "git log --oneline -3", "docker compose up -d --force-recreate"):
            self.assertFalse(denied(perms, command), command)

    def test_runner_runs_the_kit_and_recreates_containers(self):
        perms = self.perms("qualification-runner")
        for rule in ("Bash(bash qualification/kit/*)", "Bash(sh qualification/kit/*)", "Bash(./qualification/kit/*)"):
            self.assertIn(rule, perms["permissions"]["allow"])
        self.assertNotIn("Bash(* --force*)", perms["permissions"]["deny"])
        self.assertFalse(denied(perms, "docker rm --force db"))

    def test_lead_reads_the_worktrees(self):
        lead = self.perms("technical-lead")["permissions"]
        self.assertEqual(lead["additionalDirectories"], [str(self.tmp / "todo-wt")])
        self.assertNotIn("additionalDirectories", self.perms("story-implementer")["permissions"])


class StartingSessionTest(RepoCase):
    """An interactive session not yet listed by `claude agents` is not taken for a dead one."""

    def test_grace_before_a_session_counts_as_dead(self):
        module = importlib.import_module(f"deliveryctl.window.{mentions.NAME}")
        win = getattr(module, mentions.NAME.capitalize() + "Window")(self.repo)
        win.remember("s001", "story-implementer", {"session_id": "S1", "pane": "p1"})
        with mock.patch.object(module, "claude_sessions", return_value={}):
            self.assertIsNone(win.role_alive("s001", "story-implementer"))
            old = (datetime.now(timezone.utc) - timedelta(seconds=module.STARTING + 5)).isoformat()
            reg = win.sessions("s001")
            reg["story-implementer"]["started"] = old.replace("+00:00", "Z")
            from deliveryctl.core import write_json
            write_json(win._registry("s001"), reg)
            self.assertIs(win.role_alive("s001", "story-implementer"), False)
        with mock.patch.object(module, "claude_sessions", return_value={"S1": {"status": "idle"}}):
            self.assertIs(win.role_alive("s001", "story-implementer"), True)


if __name__ == "__main__":
    import unittest
    unittest.main()
