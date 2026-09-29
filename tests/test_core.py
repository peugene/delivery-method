"""Core modules: frontmatter, verdicts, configuration, git plumbing, cards, verification steps,
ports and the command line."""

import io
import shutil
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from support import RepoCase, git, write

from deliveryctl import cards, cli, config, core, frontmatter as fm, ports, verdict, verify
from deliveryctl.gitops import Git

TREE = "a" * 40


class FrontmatterTest(unittest.TestCase):
    def test_flat_subset(self):
        data, body = fm.split("---\nid: s004\nrisks: [authz, data-write]  # c\ncode: false\n"
                              "m: {a: [1, 2]}\nq: \"x: y\"\n---\n## Objective\ntext\n")
        self.assertEqual(data, {"id": "s004", "risks": ["authz", "data-write"], "code": False,
                                "m": {"a": [1, 2]}, "q": "x: y"})
        self.assertEqual(fm.section_get(body, "Objective"), "text")

    def test_rejects_block_yaml(self):
        with self.assertRaises(fm.FrontmatterError):
            fm.split("---\nrisks:\n  - authz\n---\n")

    def test_set_key_keeps_comments(self):
        text = "---\nid: s004\nstatus: draft   # draft | ready\n---\nbody\n"
        out = fm.set_key(text, "status", "ready")
        self.assertIn("status: ready  # draft | ready", out)
        self.assertTrue(out.endswith("body\n"))

    def test_meaningful(self):
        self.assertFalse(fm.meaningful("<describe>\n\n<!-- hint -->"))
        self.assertTrue(fm.meaningful("- measured: p95 < 200 ms"))


class VerdictTest(unittest.TestCase):
    def test_valid_block(self):
        text = f"notes\n\nVerdict: yes\nTree: {TREE}\nCommand: just check\nResult: exit 0\nBy: story-reviewer\n"
        v = verdict.parse(text, "review")
        self.assertTrue(v.valid, v.problems)
        self.assertEqual(v.verdict, "yes")

    def test_invalid_block(self):
        v = verdict.parse("Verdict: pass\nTree: nope\nBy: engine\nEvidence: /tmp/x.log\n", "verification")
        self.assertFalse(v.valid)
        self.assertTrue(any("Evidence outside" in p for p in v.problems))
        self.assertTrue(any("missing 'Command:'" in p for p in v.problems))

    def test_author_of_the_verdict(self):
        text = f"Verdict: yes\nTree: {TREE}\nCommand: true\nResult: ok\nBy: story-implementer\n"
        v = verdict.parse(text, "review")
        self.assertIn("By must be 'story-reviewer' for a review verdict, got 'story-implementer'", v.problems)
        self.assertFalse(verdict.parse(text.replace("Verdict: yes", "Verdict: pass"), "verification").valid)

    def test_outcome(self):
        self.assertEqual(verdict.outcome("x\nOutcome: deferred — product question\n"), ("deferred", "product question"))
        self.assertIsNone(verdict.outcome("Outcome: done\nmore text\n"))


class ConfigTest(unittest.TestCase):
    def test_defaults_and_levers(self):
        c = config.parse({"repo_role": "impl", "levers": {"review_loops": 1}}, Path("/x/todo-kotlin"))
        self.assertEqual(c.lever("review_loops"), 1)
        self.assertEqual(c.lever("verify_attempts"), 3)
        self.assertEqual(c.agent_prefix, "tk")
        self.assertEqual(c.integration, "human")

    def test_unknown_keys_fail(self):
        for data in ({"repo_role": "impl", "nope": 1}, {"repo_role": "impl", "levers": {"nope": 1}},
                     {"repo_role": "impl", "commands": {"deploy": "x"}}, {"repo_role": "x"}):
            with self.assertRaises(core.DeliveryError):
                config.parse(data, Path("/x/r"))

    def test_reinforced_risks_complete_the_defaults(self):
        c = config.parse({"repo_role": "impl", "levers": {"reinforced_risks": {
            "payment": ["adversarial-review"], "data-leak": []}}}, Path("/x/r"))
        risks = c.lever("reinforced_risks")
        self.assertEqual(risks["authz"], ["bite", "adversarial-review"])
        self.assertEqual(risks["payment"], ["adversarial-review"])
        self.assertEqual(risks["data-leak"], [])
        self.assertIn("payment", c.risks)
        self.assertEqual(config.LEVER_DEFAULTS["reinforced_risks"]["data-leak"], ["adversarial-review"])

    def test_command_substitution(self):
        c = config.parse({"repo_role": "impl", "commands": {"acceptance": "just acceptance {grep}"}}, Path("/x/r"))
        self.assertEqual(c.command("acceptance", grep="@s004"), "just acceptance @s004")
        self.assertIsNone(c.command("serve"))


class GitTest(RepoCase):
    def test_code_tree_ignores_story_folders(self):
        g = Git(self.repo)
        before = g.code_tree()
        write(self.repo / "docs/stories/s001/report.md", "Outcome: done — x\n")
        self.commit_all("report")
        self.assertEqual(g.code_tree(), before)
        write(self.repo / "src/app.txt", "v2\n")
        self.commit_all("code")
        self.assertNotEqual(g.code_tree(), before)

    def test_target_branch_and_worktree(self):
        g = Git(self.repo)
        self.assertEqual(g.target_branch(), "main")
        wt = self.tmp / "todo-wt" / "s001"
        g.worktree_add(wt, "story/s001", "origin/main")
        self.assertEqual(g.worktree_for("story/s001"), wt)
        self.assertEqual(core.main_root(wt), self.repo)

    def test_commit_with_trailers(self):
        g = Git(self.repo)
        write(self.repo / "a.txt", "a\n")
        g.commit(["a.txt"], "add a", [("Story", "s001"), ("Agent", "engine")])
        self.assertIn("Story: s001", git(self.repo, "log", "-1", "--format=%B"))


class CardsTest(RepoCase):
    READY = """---
id: s002
kind: story
title: Create a list
status: ready
depends_on: [s001]
risks: []
spec: s002
---
## Objective
Users create lists.
## Context and scope
src/lists/
## Oracle
- Functional: spec s002, AC1-AC3.
- Measured: list creation answers under 300 ms.
- Not tested by this card: offline mode.
"""

    def test_lint_and_order(self):
        write(self.repo / "backlog/s001-sign-in.md", self.READY.replace("s002", "s001")
              .replace("depends_on: [s001]", "depends_on: []"))
        write(self.repo / "backlog/s002-create-list.md", self.READY)
        write(self.repo / "backlog/t003-ci.md", "---\nid: t003\nkind: task\ntitle: CI\nstatus: draft\n---\n")
        all_cards = cards.load_all(self.repo)
        self.assertEqual(cards.lint(all_cards), [])
        ordered = cards.order(all_cards, done=set())
        self.assertEqual([(c.id, deps) for c, deps in ordered], [("s001", []), ("s002", ["s001"])])
        self.assertEqual([c.id for c, _ in cards.order(all_cards, done={"s001"})], ["s002"])

    def test_readiness_problems(self):
        write(self.repo / "backlog/s002-create-list.md",
              self.READY.replace("- Not tested by this card: offline mode.\n", "").replace("src/lists/", ""))
        problems = cards.lint(cards.load_all(self.repo))
        texts = [p for _, p in problems]
        self.assertIn("'## Context and scope' is empty", texts)
        self.assertIn("'## Oracle' needs a 'Not tested by this card:' line", texts)
        self.assertIn("depends on unknown card 's001'", texts)

    def test_merged_ids(self):
        g = Git(self.repo)
        git(self.repo, "switch", "--quiet", "-c", "story/s001")
        write(self.repo / "src/x.txt", "x\n")
        self.commit_all("work")
        git(self.repo, "switch", "--quiet", "main")
        git(self.repo, "merge", "--quiet", "--no-ff", "-m", "Merge branch 'story/s001'", "story/s001")
        self.assertEqual(cards.merged_ids(g, "main"), {"s001"})
        write(self.repo / "src/y.txt", "y\n")
        self.commit_all("Create a list (story/s002)")               # squash merged in the forge
        write(self.repo / "src/z.txt", "z\n")
        self.commit_all("Merge story/s003: x\n\nStory: s003\nApproved-By: owner@example.test")
        write(self.repo / "src/w.txt", "w\n")
        self.commit_all("a role commit\n\nStory: s004\nAgent: story-implementer")
        self.assertEqual(cards.merged_ids(g, "main"), {"s001", "s002", "s003"})
        write(self.repo / "src/v.txt", "v\n")
        self.commit_all("Merge story/s005 : Partager une liste")             # the engine's merge subject
        write(self.repo / "src/u.txt", "u\n")
        self.commit_all("s006 : Inviter un membre (story/s006) (#12)")      # its request title, squashed
        write(self.repo / "src/t.txt", "t\n")
        self.commit_all("order s007 : Retirer un membre\n\nStory: s007\nAgent: engine")
        self.assertEqual(cards.merged_ids(g, "main"), {"s001", "s002", "s003", "s005", "s006"})

    def test_title_is_required_and_a_long_one_is_noted(self):
        write(self.repo / "backlog/s001-sign-in.md", self.READY.replace("s002", "s001")
              .replace("depends_on: [s001]", "depends_on: []").replace("title: Create a list\n", ""))
        write(self.repo / "backlog/t003-ci.md", "---\nid: t003\nkind: task\ntitle:   \nstatus: draft\n---\n")
        long = "Create, rename and archive a list, with its items, from the list page and the menu"
        write(self.repo / "backlog/s002-create-list.md", self.READY.replace("Create a list", long))
        all_cards = cards.load_all(self.repo)
        self.assertEqual(cards.lint(all_cards), [("s001", cards.TITLE_REQUIRED), ("t003", cards.TITLE_REQUIRED)])
        self.assertEqual(cards.notes(all_cards), [("s002", f"title of {len(long)} characters: a short title "
                                                           "reads in a few words (3 to 8)")])
        placeholder = cards.parse(Path("backlog/s002-create-list.md"),
                                  self.READY.replace("Create a list", "<short title>"))
        self.assertEqual(placeholder.problems, [])
        self.assertIn(cards.TITLE_REQUIRED, cards.readiness(placeholder))

    def test_labels(self):
        self.assertEqual(cards.label("s004", "Partager une liste"), "s004 : Partager une liste")
        self.assertEqual(cards.label("s004", "  Partager\tune   liste "), "s004 : Partager une liste")
        for unknown in ("", None, "<titre court>"):
            self.assertEqual(cards.label("s004", unknown), "s004")
        self.assertEqual(cards.labels(["s001", "s009"], {"s001": "Sign in, then out"}),
                         "s001 : Sign in, then out; s009")
        write(self.repo / "backlog/s002-create-list.md", self.READY.replace("depends_on: [s001]", "depends_on: [s002]"))
        texts = [p for _, p in cards.lint(cards.load_all(self.repo))]
        self.assertIn("dependency cycle: s002 : Create a list -> s002 : Create a list", texts)

    def test_spec_is_a_spec_story_id(self):
        text = self.READY.replace("spec: s002", "spec: s002 $(touch x)")
        card = cards.parse(Path("backlog/s002-create-list.md"), text)
        self.assertIn("spec must be a spec story id like s004, got 's002 $(touch x)'", card.problems)
        self.assertEqual(cards.parse(Path("backlog/s002-create-list.md"), self.READY).problems, [])


class VerifyStepsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dm-steps-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_plan_steps(self):
        commands = {"check": "check {port}", "acceptance": "run {grep} {port}"}
        c = config.parse({"repo_role": "impl", "commands": commands}, Path("/x/r"))
        card = SimpleNamespace(id="s001", spec="s001", code=True)
        self.assertEqual(verify.plan_steps(c, card, ["src/a.kt"], 31001),
                         ([("check", "check 31001"), ("acceptance", "run @s001 31001")], ""))
        for changes, why in (({"spec": ""}, "no spec story"), ({"code": False}, "card without code")):
            steps, reason = verify.plan_steps(c, SimpleNamespace(**{**vars(card), **changes}), ["src/a.kt"], 31001)
            self.assertEqual((len(steps), reason), (1, why))
        self.assertEqual(verify.plan_steps(c, card, ["README.md", "docs/stories/s001/report.md"])[1],
                         "documentation only")
        bare = config.parse({"repo_role": "impl", "commands": {"check": "true"}}, Path("/x/r"))
        self.assertEqual(verify.plan_steps(bare, card, ["src/a.kt"])[1], "no acceptance command")

    def test_output_is_streamed_and_leftovers_do_not_hold_the_step(self):
        log = self.tmp / "verify.log"
        start = time.monotonic()
        res = verify.run_step("(sleep 5.25; echo late) & echo '3 passed'; exit 0", self.tmp, log)
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual((res["exit"], res["tests"]), (0, 3))
        text = log.read_text()
        self.assertIn("3 passed", text)
        self.assertIn("[exit 0,", text)
        self.assertNotIn("\nlate\n", text)

    @unittest.skipUnless(shutil.which("pgrep"), "pgrep is needed")
    def test_timeout_stops_the_whole_process_group(self):
        start = time.monotonic()
        res = verify.run_step("sleep 30.25 & sleep 30.25", self.tmp, self.tmp / "v.log", timeout=1, grace=1)
        self.assertEqual(res["exit"], 124)
        self.assertLess(time.monotonic() - start, 6)
        left = subprocess.run(["pgrep", "-f", "sleep 30.25"], capture_output=True, text=True).stdout
        self.assertEqual(left.strip(), "")


class PortsTest(RepoCase):
    def test_port_of_a_story_and_of_another_scope(self):
        c = config.parse({"repo_role": "impl"}, self.repo)
        first = ports.port(c, "s004")
        self.assertTrue(str(first).startswith("31"))
        self.assertEqual(ports.port(c, "s004"), first)
        other = ports.port(c, "nightly-day")
        self.assertNotEqual(other, first)
        ports.release(c, "s004")
        self.assertNotIn("s004", core.read_json(self.repo / ".delivery/run/ports.json", {}))


class CliTest(RepoCase):
    CARD = CardsTest.READY.replace("id: s002", "id: t001").replace("kind: story", "kind: task").replace(
        "depends_on: [s001]", "depends_on: []")

    def call(self, *argv) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_usage_errors_exit_1(self):
        for argv in (["verify"], ["story", "open"], ["cards", "frobnicate"], ["gate", "s001", "--bogus"]):
            self.assertEqual(self.call(*argv)[0], core.EXIT_ERROR, argv)
        self.assertEqual(self.call("--version")[0], core.EXIT_OK)

    def test_cards_list_reads_the_target_branch(self):
        write(self.repo / "delivery.toml", 'repo_role = "impl"\nforge = "github"\n')
        self.commit_all("settings")
        git(self.repo, "push", "--quiet", "origin", "main")
        write(self.repo / "backlog/t001-ci.md", self.CARD)          # ready in the checkout only
        code, out = self.call("cards", "list")
        self.assertEqual((code, out), (core.EXIT_OK, ""))
        code, out = self.call("cards", "lint")
        self.assertEqual(code, core.EXIT_OK, out)
        self.commit_all("t001 ready")
        git(self.repo, "push", "--quiet", "origin", "main")
        self.assertIn("t001 : Create a list — task, ready", self.call("cards", "list")[1])

    def test_cards_name_their_dependencies_and_lint_names_the_card(self):
        write(self.repo / "delivery.toml", 'repo_role = "impl"\nforge = "github"\n')
        write(self.repo / "backlog/t001-ci.md", self.CARD)
        write(self.repo / "backlog/t002-deploy.md", self.CARD.replace("t001", "t002")
              .replace("Create a list", "Deploy on push").replace("depends_on: []", "depends_on: [t001]"))
        self.commit_all("cards")
        git(self.repo, "push", "--quiet", "origin", "main")
        listed = self.call("cards", "list")[1].splitlines()
        self.assertEqual(listed, ["t001 : Create a list — task, ready",
                                  "t002 : Deploy on push — task, ready, depends on t001 : Create a list"])
        ordered = self.call("cards", "order")[1].splitlines()
        self.assertEqual(ordered, ["t001 : Create a list — task, ready",
                                   "t002 : Deploy on push — task, ready (waits for t001 : Create a list)"])
        write(self.repo / "backlog/t002-deploy.md",
              self.CARD.replace("t001", "t002").replace("title: Create a list\n", ""))
        long = "Create, rename and archive a list, with its items, from the list page and the menu"
        write(self.repo / "backlog/t001-ci.md", self.CARD.replace("Create a list", long))
        code, out = self.call("cards", "lint")
        self.assertEqual(code, core.EXIT_RED, out)
        self.assertIn("t002 — title: a short title is required\n", out)
        self.assertIn(f"note: t001 : {long} — title of {len(long)} characters", out)
        write(self.repo / "backlog/t002-deploy.md", self.CARD.replace("t001", "t002"))
        code, out = self.call("cards", "lint")
        self.assertEqual(code, core.EXIT_OK, out)                   # a long title is a note, not a problem
        self.assertIn("note: t001 : ", out)


if __name__ == "__main__":
    unittest.main()
