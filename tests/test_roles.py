"""Role files: who may write a verdict, which commands the prefix rules miss, what the runner and
the lead may reach; and the grace a starting interactive session gets before it counts as dead."""

import importlib
import os
import re
from datetime import datetime, timedelta, timezone
from unittest import mock

from support import ROOT, RepoCase, git, write

from deliveryctl import config, roles
from deliveryctl.core import EXIT_PRECONDITION, DeliveryError
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
        write(self.repo / "delivery.toml", 'repo_role = "impl"\nforge = "github"\n[commands]\ncheck = "true"\n')
        self.cfg = config.load(self.repo)
        self.wt = self.tmp / "todo-wt" / "s001"

    def perms(self, role: str) -> dict:
        return roles.permissions(self.cfg, role, self.wt, "s001")

    def test_launch_uses_the_project_copy_of_the_agent(self):
        self.wt.mkdir(parents=True)
        with self.assertRaises(DeliveryError) as ctx:
            roles.launch(self.cfg, "story-implementer", self.wt, "s001", "go", headless=True)
        self.assertEqual(ctx.exception.code, EXIT_PRECONDITION)
        self.assertIn("deliveryctl init --upgrade", ctx.exception.message)
        write(self.wt / ".claude" / "agents" / "story-implementer.md", "---\nname: story-implementer\n---\n")
        spec = roles.launch(self.cfg, "story-implementer", self.wt, "s001", "go", headless=True)
        argv = spec["argv"]
        self.assertEqual(argv[argv.index("--agent") + 1], "story-implementer")
        self.assertNotIn("--plugin-dir", argv)
        self.assertEqual(spec["env"]["PATH"].split(os.pathsep)[0], str(self.wt / ".delivery"))
        self.assertIn(f"PATH={self.wt}/.delivery:", roles.shell_line(spec))
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "project")

    def test_the_lead_runs_the_renamed_command(self):
        self.assertEqual(roles.PROMPTS["technical-lead"].format(campaign="c1"), "/run-campaign c1")
        self.assertTrue((ROOT / "commands" / "run-campaign.md").exists())
        self.assertFalse((ROOT / "commands" / "run.md").exists())

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

    def test_archived_brainstorms_are_out_of_reach(self):
        for role in roles.UNATTENDED:
            perms = self.perms(role)
            self.assertIn("Read(**/docs/maybe/**)", perms["permissions"]["deny"], role)
            self.assertTrue(denied(perms, "cat docs/maybe/2026-01-01-idea.md"), role)
            self.assertTrue(denied(perms, "grep -r cache docs/maybe/"), role)
            self.assertFalse(denied(perms, "cat docs/stories/s001/order.md"), role)

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


class NamesTest(RepoCase):
    """Role prompts and the story window name the card by its label (CONTRACTS.md §5)."""

    def test_prompts_carry_the_label(self):
        prompt = roles.PROMPTS["story-implementer"].format(id="s004", label="s004 : Partager une liste",
                                                           mode="implement")
        self.assertEqual(prompt, "Story s004 : Partager une liste — read docs/stories/s004/order.md and carry it "
                                 "out. Mode: implement.")
        prompt = roles.PROMPTS["story-reviewer"].format(id="s004", label="s004 : Partager une liste",
                                                        tree="t" * 40, target="origin/main", loop=1)
        self.assertTrue(prompt.startswith("Story s004 : Partager une liste — review the change at code tree"))

    def test_story_window_is_named_by_the_card(self):
        write(self.repo / "backlog/s004-share.md", "---\nid: s004\nkind: story\ntitle: Partager une liste\n"
                                                   "status: draft\nspec: s004\n---\n")
        self.commit_all("card")
        git(self.repo, "push", "--quiet", "origin", "main")
        module = importlib.import_module(f"deliveryctl.window.{mentions.NAME}")
        win = getattr(module, mentions.NAME.capitalize() + "Window")(self.repo)
        calls = []

        def fake(*args, **_):
            calls.append(args)
            return {}                     # no workspace id: open_story stops after the creation
        with mock.patch.object(module, "_" + mentions.NAME, side_effect=fake):
            win.open_story("s004", self.tmp / "todo-wt" / "s004")
            win.open_story("s009", self.tmp / "todo-wt" / "s009")
            win.open_story("0.2.0", self.tmp / "todo-wt" / "qualification-0.2.0")
        labels = [args[args.index("--label") + 1] for args in calls if args[:2] == ("workspace", "create")]
        self.assertEqual(labels, ["todo-s004 : Partager une liste", "todo-s009", "todo-0.2.0"])


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
