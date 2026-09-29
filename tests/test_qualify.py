"""Qualification (open, lint, run, submit) and the nightly full UI suite, with a fake runner."""

import io
import json
import os
import re
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from support import RepoCase, git, write

from deliveryctl import config, core, nightly, qualify

FAKE = Path(__file__).resolve().parent / "e2e" / "fake_runner.py"
PLAN = """# Qualification plan

## Surface

| Entry point | Kind | Controls |
|---|---|---|
| GET /lists/{id} | route | Q1, Q2 |
| purge | scheduled | not covered — no scheduler yet |

## Controls

### Q1 — the owner reads a list   [run]
Targets: s004 · GET /lists/{id}
Do: create a list, read it
Expect: 200 with the list

### Q2 — a stranger cannot read a list   [run, negative]
Targets: s004 · GET /lists/{id}
Touches: src/**/share/**
Do: read the list of A as C
Expect: 404
"""
REPORT = """# Qualification report 0.1.0

Tree: {tree}
Spec: none
Env: local machine, chromium

## Results

| Q | Mode | Result | Proof |
|---|---|---|---|
| Q1 | run | pass | curl → 200 |
| Q2 | run, negative | pass | curl → 404 |

## Anomalies

none

## Read

No documentation promise in this increment.

## Run

Both controls played on a fresh install.

Verdict: accepted
Tree: {tree}
Command: curl -s localhost
Result: 2 pass, 0 fail
By: qualification-lead
"""


class QualifyCase(RepoCase):
    acceptance = "echo '3 passed'"

    def setUp(self):
        super().setUp()
        write(self.repo / "delivery.toml",
              f'repo_role = "impl"\nforge = "github"\n[commands]\ncheck = "true"\n'
              f'acceptance = "{self.acceptance}"\n')
        write(self.repo / ".gitignore", ".delivery/run/\nqualification/work/\n")
        self.commit_all("setup")
        git(self.repo, "push", "--quiet", "origin", "main")
        self.cfg = config.load(self.repo)

    def quiet(self, func, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = func(*args)
        return result, out.getvalue() + err.getvalue()


class QualifyTest(QualifyCase):
    def opened(self):
        qualify.open_qualification(self.cfg, "0.1.0")
        wt = self.tmp / "todo-wt" / "qualification-0.1.0"
        base = git(wt, "rev-parse", "HEAD")
        tree = qualify.Git(wt).code_tree(base)
        return wt, tree

    def fill(self, wt, tree, plan=PLAN, report=REPORT):
        write(wt / "qualification/plan.md", plan)
        write(wt / "qualification/reports/0.1.0.md", report.replace("{tree}", tree))

    def problems(self):
        return "\n".join(qualify.lint(self.cfg, "0.1.0")[1])

    def test_open_creates_worktree_and_files(self):
        out = qualify.open_qualification(self.cfg, "0.1.0")
        wt, tree = self.opened()
        self.assertIn(str(wt), out)
        self.assertEqual(git(wt, "branch", "--show-current"), "qualification/0.1.0")
        self.assertTrue((wt / "qualification/plan.md").exists())
        report = (wt / "qualification/reports/0.1.0.md").read_text()
        self.assertIn(f"Tree: {tree}", report)
        self.assertNotIn("<incr>", report)
        order = (wt / qualify.ORDER).read_text()
        self.assertIn(f"base: {git(wt, 'rev-parse', 'HEAD')}", order)
        self.assertEqual(qualify.ORDER, "qualification/order.md")
        self.assertFalse(qualify.Git(wt).ok("check-ignore", "-q", qualify.ORDER))
        (wt / "qualification/plan.md").write_text("kept\n")
        self.assertIn("(existing)", qualify.open_qualification(self.cfg, "0.1.0"))
        self.assertEqual((wt / "qualification/plan.md").read_text(), "kept\n")

    def test_lint_green_then_red_on_skeleton(self):
        wt, tree = self.opened()
        code, out = self.quiet(qualify.main, Namespace(action="lint", increment="0.1.0"))
        self.assertEqual(code, core.EXIT_RED)
        self.assertIn("qualification: red", out)
        self.assertRegex(out, r"qualification/plan\.md:\d+: Surface row is not filled")
        self.fill(wt, tree)
        self.assertEqual(self.problems(), "")

    def test_lint_catches_duplicate_numbers(self):
        wt, tree = self.opened()
        self.fill(wt, tree, plan=PLAN.replace("### Q2", "### Q1"))
        self.assertRegex(self.problems(), r"plan\.md:\d+: Q1 : a stranger cannot read a list — number already "
                                          r"used by Q1 : the owner reads a list \(line \d+\)")

    def test_lint_catches_missing_expect(self):
        wt, tree = self.opened()
        self.fill(wt, tree, plan=PLAN.replace("Expect: 404\n", ""))
        self.assertIn("Q2 : a stranger cannot read a list — missing 'Expect:' line", self.problems())

    def test_control_heading_with_a_colon_and_control_labels(self):
        wt, tree = self.opened()
        self.fill(wt, tree, plan=PLAN.replace("### Q2 — a stranger", "### Q2 : a stranger"))
        self.assertEqual(self.problems(), "")
        self.assertEqual(qualify.control_label(17, "un compte non invité ne lit pas une liste partagée"),
                         "Q17 : un compte non invité ne lit pas une liste partagée")
        self.assertEqual(qualify.control_label(17, "<title>"), "Q17")

    def test_result_rows_name_their_control(self):
        wt, tree = self.opened()
        report = (REPORT.replace("| Q1 | run | pass", "| Q1 : the owner reads a list | run | pass")
                  .replace("| Q2 | run, negative | pass", "| Q2 : a stranger cannot read a list | run, negative | ok"))
        self.fill(wt, tree, report=report)
        problems = self.problems()
        self.assertNotIn("Q1", problems)
        self.assertIn("Q2 : a stranger cannot read a list — result must be one of", problems)
        self.assertNotIn("without a result row", problems)

    def test_lint_catches_malformed_control_heading(self):
        wt, tree = self.opened()
        self.fill(wt, tree, plan=PLAN.replace("### Q2 — a stranger cannot read a list   [run, negative]",
                                              "### Q2bis a stranger cannot read a list (run)"))
        self.assertIn("control heading must read", self.problems())

    def test_lint_catches_invalid_verdict_and_tree(self):
        wt, tree = self.opened()
        self.fill(wt, tree, report=REPORT.replace("Verdict: accepted", "Verdict: maybe"))
        self.assertIn("Verdict must be one of accepted", self.problems())
        self.fill(wt, "f" * 40)
        self.assertIn("is not the code tree of the qualified commit", self.problems())

    def test_close_removes_the_worktree_and_keeps_the_branch(self):
        wt, _ = self.opened()
        self.assertIn("branch qualification/0.1.0 kept", qualify.close(self.cfg, "0.1.0"))
        self.assertFalse(wt.exists())
        self.assertIn("qualification/0.1.0", git(self.repo, "branch", "--list", "qualification/0.1.0"))

    def test_lint_catches_tmp_proof_result_value_and_author(self):
        wt, tree = self.opened()
        report = (REPORT.replace("curl → 404", "/tmp/out.log").replace("| Q1 | run | pass", "| Q1 | run | ok")
                  .replace("By: qualification-lead", "By: qualification-runner"))
        self.fill(wt, tree, report=report)
        problems = self.problems()
        self.assertIn("Q1 : the owner reads a list — result must be one of pass, fail, blocked, not-run", problems)
        self.assertIn("a proof is never a path under /tmp", problems)
        self.assertIn("a qualification verdict is proposed by: qualification-lead", problems)

    def test_lint_catches_uncovered_entry_point_and_missing_result(self):
        wt, tree = self.opened()
        plan = PLAN.replace("| purge |", "| POST /lists | route | |\n| purge |")
        report = REPORT.replace("| Q2 | run, negative | pass | curl → 404 |\n", "")
        self.fill(wt, tree, plan=plan, report=report)
        problems = self.problems()
        self.assertIn("entry point without a control", problems)
        self.assertIn("Q2 : a stranger cannot read a list — control of the plan without a result row", problems)

    def refused(self, needle):
        with self.assertRaises(core.DeliveryError) as ctx:
            qualify.start_runner(self.cfg, "0.1.0")
        self.assertEqual(ctx.exception.code, core.EXIT_PRECONDITION)
        self.assertIn(needle, ctx.exception.message)

    def test_run_requires_filled_and_committed_order_then_starts_runner(self):
        wt, _ = self.opened()
        self.refused("Controls to run")
        order = wt / qualify.ORDER
        text = order.read_text()
        for heading, value in (("Objective", "Check sharing."), ("Controls to run", "Q1, Q2"),
                               ("Environment", "just up on port 31900; just down")):
            text = re.sub(rf"(## {heading}\n)<[^\n]*>", rf"\g<1>{value}", text)
        order.write_text(text)
        self.refused("uncommitted changes")
        git(wt, "add", "qualification")
        git(wt, "commit", "--quiet", "-m", "qualify 0.1.0: order")
        order.write_text(text.replace("Check sharing.", "Check sharing again."))
        self.refused("uncommitted changes")
        git(wt, "commit", "--quiet", "-am", "qualify 0.1.0: order, second pass")
        os.environ["DELIVERY_FAKE_WINDOW"] = "1"
        os.environ["DELIVERY_FAKE_AGENT"] = str(FAKE)
        out = qualify.start_runner(self.cfg, "0.1.0")
        self.assertIn("qualification-runner started for 0.1.0", out)
        seen = (wt / "qualification/work/runner.txt").read_text()
        prompt = qualify.roles.PROMPTS["qualification-runner"].format(id="0.1.0")
        self.assertIn(f"qualification-runner 0.1.0 {prompt}", seen)
        self.assertIn("Check sharing again.", git(wt, "show", f"HEAD:{qualify.ORDER}"))

    def test_prompts_name_the_committed_order(self):
        root = Path(__file__).resolve().parents[1]
        for rel in ("agents/qualification-lead.md", "agents/qualification-runner.md",
                    "commands/qualify.md"):
            self.assertIn(qualify.ORDER, (root / rel).read_text(encoding="utf-8"), rel)
        self.assertIn("commite", (qualify.TEMPLATES / "order.md").read_text(encoding="utf-8"))
        for folder in ("agents", "commands", "skills", "templates"):
            for path in (root / folder).rglob("*.md"):
                self.assertNotIn("qualification/work/order.md", path.read_text(encoding="utf-8"), path)

    def test_submit_is_human_and_opens_a_merge_request(self):
        wt, tree = self.opened()
        self.fill(wt, tree)
        git(wt, "add", "qualification")
        git(wt, "commit", "--quiet", "-m", "qualification 0.1.0")
        os.environ["DELIVERY_ROLE"] = "qualification-runner"
        try:
            with self.assertRaises(core.DeliveryError) as ctx:
                qualify.submit(self.cfg, "0.1.0")
            self.assertEqual(ctx.exception.code, core.EXIT_REFUSED)
        finally:
            os.environ.pop("DELIVERY_ROLE")
        self.assertEqual(qualify.submit(self.cfg, "0.1.0"), "https://forge.test/pr/1")
        self.assertIn("pr create", (self.forge_dir / "calls").read_text())

    def test_invalid_increment(self):
        with self.assertRaises(core.DeliveryError):
            qualify.check_increment("../x")


class NightlyGreenTest(QualifyCase):
    def test_green_suite_leaves_nothing_behind(self):
        code, out = self.quiet(nightly.run, self.cfg)
        self.assertEqual(code, core.EXIT_OK, out)
        day = core.today()
        self.assertFalse((self.tmp / "todo-wt" / f"nightly-{day}").exists())
        self.assertEqual(git(self.repo, "branch", "--list", f"anomalies/{day}"), "")
        events = queue(self)
        self.assertEqual(events[-1]["category"], "summary")
        self.assertIn("3 passed", events[-1]["text"])


class NightlyRedTest(QualifyCase):
    acceptance = "echo '2 passed, 1 failed'; exit 1"

    def setUp(self):
        super().setUp()
        os.environ["DELIVERY_FAKE_WINDOW"] = "1"
        os.environ["DELIVERY_FAKE_AGENT"] = str(FAKE)

    def check_card(self):
        day = core.today()
        branch = f"anomalies/{day}"
        card = git(self.repo, "show", f"{branch}:backlog/a001-sign-in-fails.md")
        head = git(self.repo, "rev-parse", "--short=7", "origin/main")
        self.assertIn("kind: anomaly", card)
        self.assertIn(f"found: nightly-{day}@{head}", card)
        self.assertFalse((self.tmp / "todo-wt" / f"nightly-{day}").exists())
        self.assertEqual(queue(self)[-1]["category"], "night-anomalies")
        notified = json.loads((self.repo / ".delivery/run/notified.json").read_text())
        self.assertIn(f"night:{day}", notified)
        return git(self.repo, "log", "-1", "--format=%B", branch)

    def test_red_suite_gives_anomaly_cards_on_a_branch(self):
        code, out = self.quiet(nightly.run, self.cfg)
        self.assertEqual(code, core.EXIT_RED, out)
        self.assertIn("1 anomaly card(s) (a001 : Sign in fails)", out)
        self.assertIn("Agent: qualification-runner", self.check_card())

    def test_request_body_names_the_cards(self):
        path = self.tmp / "nightly.log"
        card = nightly.cards.parse(Path("backlog/a001-sign-in-fails.md"),
                                   "---\nid: a001\nkind: anomaly\ntitle: Sign in fails\nstatus: to-triage\n"
                                   "spec: s001\nfound: nightly-x@abc\n---\n")
        body = nightly._request_body(core.today(), "abc1234", "just acceptance", {"exit": 1}, [card], [], path,
                                     {"s001": "Sign in"})
        self.assertIn("- `backlog/a001-sign-in-fails.md` — a001 : Sign in fails — spec s001 : Sign in", body)

    def test_runner_is_asked_for_a_short_title(self):
        self.assertIn("title: the fault in 3 to 8 words", nightly.PROMPT)

    def test_engine_commits_cards_left_by_the_runner(self):
        os.environ["FAKE_RUNNER_NO_COMMIT"] = "1"
        try:
            code, out = self.quiet(nightly.run, self.cfg)
        finally:
            os.environ.pop("FAKE_RUNNER_NO_COMMIT")
        self.assertEqual(code, core.EXIT_RED, out)
        self.assertIn("Agent: engine", self.check_card())

    def test_runner_that_cannot_start_leaves_nothing_behind(self):
        from unittest import mock
        day = core.today()
        failure = core.DeliveryError(core.EXIT_TOOL, "the 'claude' command is not available")
        for _ in range(2):          # the second run of the day is not refused
            with mock.patch.object(nightly, "_run_runner", side_effect=failure):
                with self.assertRaises(core.DeliveryError) as ctx:
                    self.quiet(nightly.run, self.cfg)
            self.assertEqual(ctx.exception.code, core.EXIT_TOOL)
            self.assertFalse((self.tmp / "todo-wt" / f"nightly-{day}").exists())
            self.assertEqual(git(self.repo, "branch", "--list", f"anomalies/{day}"), "")
        self.assertTrue((self.repo / f".delivery/run/logs/nightly-{day}.log").exists())


class NightlyLeftoverTest(QualifyCase):
    def test_leftover_branch_without_commits_is_dropped(self):
        day = core.today()
        wt = self.tmp / "todo-wt" / f"nightly-{day}"
        git(self.repo, "worktree", "add", "--quiet", "-b", f"anomalies/{day}", str(wt), "origin/main")
        code, out = self.quiet(nightly.run, self.cfg)
        self.assertEqual(code, core.EXIT_OK, out)
        self.assertFalse(wt.exists())
        self.assertEqual(git(self.repo, "branch", "--list", f"anomalies/{day}"), "")

    def test_leftover_branch_with_cards_is_refused_with_the_command(self):
        day = core.today()
        wt = self.tmp / "todo-wt" / f"nightly-{day}"
        git(self.repo, "worktree", "add", "--quiet", "-b", f"anomalies/{day}", str(wt), "origin/main")
        write(wt / "backlog" / "a001-x.md", "---\nid: a001\n---\n")
        self.commit_all("card", cwd=wt)
        with self.assertRaises(core.DeliveryError) as ctx:
            self.quiet(nightly.run, self.cfg)
        self.assertEqual(ctx.exception.code, core.EXIT_PRECONDITION)
        self.assertIn(f"git worktree remove --force {wt} && git branch -D anomalies/{day}", ctx.exception.message)


def queue(case):
    path = case.home / ".local/state/delivery-method/journal-queue.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


if __name__ == "__main__":
    import unittest
    unittest.main()
