"""End-to-end story cycle with a fake agent, local forge, terminal-free fake window."""

import io
import json
import os
import stat
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from support import RepoCase, git, sh, write

from deliveryctl import cards, config, core, gate, journal, ports, story, verify

FAKE = Path(__file__).resolve().parent / "e2e" / "fake_agent.py"
CARD = """---
id: s001
kind: story
title: Sign in
status: ready
depends_on: []
risks: []
spec: s001
---
## Objective
Users sign in.
## Context and scope
src/app.txt
## Oracle
- Functional: spec s001, AC1.
- Not tested by this card: password reset.
"""
ORDER = """---
id: s001
campaign: run-test
issued-by: technical-lead
base: {base}
---
## Objective
Sign in works.
## Decisions
none
## Proposal
Append a line.
## Constraints
src/app.txt only.
## Read at base — re-verify, do not trust
- src/app.txt holds v1 (src/app.txt:1, read)
## Reinforced checks
none
## Deliverables
- feature line — proof: just check → exit 0
"""


FAKE_GH = """#!{python}
import json, sys
from pathlib import Path
state, calls = Path({state!r}), Path({calls!r})
with calls.open("a") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\\n")
now = state.read_text().strip() if state.exists() else ""
if sys.argv[1:3] == ["pr", "view"]:
    if now == "DOWN":
        sys.exit("HTTP 403: API rate limit exceeded")
    if not now:
        sys.exit('no pull requests found for branch "story/s001"')
    print(json.dumps({{"url": "https://forge.test/pr/1", "state": now, "statusCheckRollup": []}}))
elif sys.argv[1:3] == ["pr", "create"]:
    state.write_text("OPEN")
    print("https://forge.test/pr/1")
else:
    sys.exit(2)
"""


class StoryCycleTest(RepoCase):
    def setUp(self):
        super().setUp()
        os.environ["DELIVERY_FAKE_WINDOW"] = "1"
        os.environ["DELIVERY_FAKE_AGENT"] = str(FAKE)
        write(self.repo / "backlog/s001-sign-in.md", CARD)
        write(self.repo / ".gitignore", ".delivery/run/\ndocs/stories/*/work/\n")
        self.configure()

    def configure(self, top="", commands="", levers="", forge="none"):
        check = "grep -q BROKEN src/app.txt && exit 1 || echo '1 passed'"
        write(self.repo / "delivery.toml",
              f'repo_role = "impl"\nforge = "{forge}"\nintegration = "human"\n{top}'
              f'[commands]\ncheck = "{check}"\n{commands}[levers]\n{levers}')
        self.commit_all("settings")
        git(self.repo, "push", "--quiet", "origin", "main")
        self.cfg = config.load(self.repo)

    def fake(self, **values):
        """Set FAKE_* variables for the rest of the test."""
        for key, value in values.items():
            os.environ[f"FAKE_{key}"] = value

    def wt(self, card="s001") -> Path:
        return story.Git(self.repo).worktree_for(f"story/{card}")

    def modes(self, card="s001") -> list[str]:
        path = self.wt(card) / "docs/stories" / card / "work/fake-modes"
        return path.read_text().splitlines() if path.exists() else []

    def events(self, category=None) -> list[dict]:
        path = journal.queue_path()
        lines = path.read_text().splitlines() if path.exists() else []
        return [e for e in map(json.loads, filter(str.strip, lines)) if category in (None, e["category"])]

    def notified(self) -> dict:
        return json.loads((self.repo / ".delivery/run/notified.json").read_text())

    def drive(self, limit=12):
        st = story.state(self.cfg, "s001")
        for _ in range(limit):
            st = story.next_step(self.cfg, "s001")
            if st.name in story.STOPPED + ("submitted", "merged", "closed"):
                return st
        return st

    def open(self, card="s001", text=None, start=True):
        order = story.prepare(self.cfg, card)
        base = git(self.repo, "rev-parse", "origin/main")
        order.write_text((text or ORDER).replace("{base}", base).replace("s001", card))
        return story.open_story(self.cfg, card, start=start)

    def test_nominal_cycle_and_local_merge(self):
        self.open()
        st = self.drive()
        self.assertEqual(st.name, "submitted", story.render(st))
        wt = Path(st.worktree)
        self.assertEqual(gate.check(story.Git(wt), "s001"), [])
        summary = story.merge(self.cfg, "s001")
        self.assertIn("merged story/s001", summary)
        log = git(self.repo, "log", "-1", "--format=%B")
        self.assertIn("Story: s001", log)
        self.assertIn("Approved-By: owner@example.test", log)
        self.assertEqual(story.state(self.cfg, "s001").name, "merged")
        story.close(self.cfg, "s001")
        self.assertEqual(story.state(self.cfg, "s001").name, "closed")
        self.assertIn("feature s001", (self.repo / "src/app.txt").read_text())

    def test_review_no_then_fix_then_yes(self):
        os.environ["FAKE_REVIEW"] = "no-once"
        try:
            self.open()
            st = self.drive()
        finally:
            os.environ.pop("FAKE_REVIEW")
        self.assertEqual(st.name, "submitted", story.render(st))
        self.assertEqual(st.review_noes, 1)
        self.assertIn("story-implementer fix-review", self.modes())
        self.assertEqual(self.events("resume"), [])

    def test_red_verification_is_fixed(self):
        os.environ["FAKE_BREAK"] = "1"
        try:
            self.open()
            st = self.drive()
        finally:
            os.environ.pop("FAKE_BREAK")
        self.assertEqual(st.name, "submitted", story.render(st))
        self.assertEqual(st.verify_fails, 1)
        self.assertIn("story-implementer fix-verification", self.modes())
        self.assertEqual(self.events("resume"), [])

    def test_deferred_story_stops(self):
        os.environ["FAKE_IMPL"] = "deferred"
        try:
            self.open()
            st = self.drive()
        finally:
            os.environ.pop("FAKE_IMPL")
        self.assertEqual(st.name, "deferred")

    def test_merge_refused_in_role_session(self):
        self.open()
        self.drive()
        os.environ["DELIVERY_ROLE"] = "story-implementer"
        try:
            with self.assertRaises(core.DeliveryError) as ctx:
                story.merge(self.cfg, "s001")
            self.assertEqual(ctx.exception.code, core.EXIT_REFUSED)
        finally:
            os.environ.pop("DELIVERY_ROLE")

    def test_gate_refuses_protected_paths(self):
        self.open()
        st = self.drive()
        wt = Path(st.worktree)
        write(wt / "delivery.toml", (wt / "delivery.toml").read_text() + "\n# touched\n")
        git(wt, "add", "delivery.toml")
        git(wt, "commit", "--quiet", "-m", "touch settings")
        problems = gate.check(story.Git(wt), "s001")
        self.assertTrue(any("protected path: delivery.toml" in p for p in problems), problems)
        self.assertTrue(any("not the current code tree" in p for p in problems), problems)

    def test_show_plan_stops_on_plan_ready_then_go(self):
        write(self.repo / "backlog/s001-sign-in.md", CARD.replace("spec: s001", "spec: s001\nshow_plan: true"))
        self.commit_all("show plan")
        git(self.repo, "push", "--quiet", "origin", "main")
        self.open()
        st = self.drive()
        self.assertEqual(st.name, "plan-ready", story.render(st))
        st = story.next_step(self.cfg, "s001", go=True)
        st = self.drive()
        self.assertEqual(st.name, "submitted", story.render(st))
        self.assertIn("story-implementer implement-approved-plan", self.modes())

    def test_close_stopped_story_is_human(self):
        os.environ["FAKE_IMPL"] = "deferred"
        try:
            self.open()
            self.drive()
        finally:
            os.environ.pop("FAKE_IMPL")
        os.environ["DELIVERY_ROLE"] = "technical-lead"
        try:
            with self.assertRaises(core.DeliveryError):
                story.close(self.cfg, "s001")
        finally:
            os.environ.pop("DELIVERY_ROLE")
        self.assertIn("branch kept", story.close(self.cfg, "s001"))
        self.assertIn("story/s001", git(self.repo, "branch", "--list", "story/s001"))

    def test_stale_order_base_is_refused(self):
        write(self.repo / "backlog/s002-lists.md", CARD.replace("s001", "s002").replace("depends_on: []", "depends_on: [s001]"))
        self.commit_all("s002")
        git(self.repo, "push", "--quiet", "origin", "main")
        old_base = git(self.repo, "rev-parse", "origin/main")
        self.open()
        self.drive()
        story.merge(self.cfg, "s001")
        git(self.repo, "push", "--quiet", "origin", "main")
        order = story.prepare(self.cfg, "s002")
        order.write_text(ORDER.replace("{base}", old_base).replace("s001", "s002"))
        with self.assertRaises(core.DeliveryError) as ctx:
            story.open_story(self.cfg, "s002")
        self.assertIn("re-anchor", ctx.exception.message)
        self.assertIn("anchored before s001 : Sign in was merged", ctx.exception.message)

    def test_open_requires_dependencies_and_order(self):
        write(self.repo / "backlog/s002-lists.md", CARD.replace("s001", "s002").replace("Sign in", "Create a list")
              .replace("depends_on: []", "depends_on: [s001]"))
        self.commit_all("s002")
        git(self.repo, "push", "--quiet", "origin", "main")
        story.prepare(self.cfg, "s002")
        with self.assertRaises(core.DeliveryError) as ctx:
            story.open_story(self.cfg, "s002")
        self.assertIn("s002 : Create a list depends on cards not done yet: s001 : Sign in", ctx.exception.message)

    # -- chaining in one call (the detached `story next` of the Stop hook) ---------------------
    def test_one_next_verifies_then_starts_the_reviewer(self):
        self.open()
        self.assertEqual(story.state(self.cfg, "s001").name, "to-verify")
        st = story.next_step(self.cfg, "s001")
        self.assertEqual(st.name, "submitted", story.render(st))
        self.assertIn("story-reviewer loop 1", self.modes())

    def test_after_stop_runs_next_then_sweeps(self):
        self.open()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(story.after_stop("s001"), 0)
        self.assertEqual(story.state(self.cfg, "s001").name, "submitted")

    def test_wait_chains_until_a_stop(self):
        self.open()
        st = story.wait(self.cfg, "s001", timeout=60)
        self.assertEqual(st.name, "submitted", story.render(st))
        self.assertFalse(st.extra.get("timeout"))

    # -- bounds --------------------------------------------------------------------------------
    def test_verify_bound_is_notified_and_journaled_once(self):
        self.configure(levers="verify_attempts = 0\n")
        self.fake(BREAK="always")
        self.open()
        st = story.next_step(self.cfg, "s001")
        self.assertEqual(st.name, "verify-exhausted", story.render(st))
        story.next_step(self.cfg, "s001")
        self.assertIn("s001:verify-exhausted", self.notified())
        self.assertEqual(len(self.events("verify-exhausted")), 1)

    def test_review_bound(self):
        self.configure(levers="review_loops = 0\n")
        self.fake(REVIEW="no")
        self.open()
        st = self.drive()
        self.assertEqual(st.name, "review-exhausted", story.render(st))
        story.next_step(self.cfg, "s001")      # what the Stop hook of the reviewer triggers
        self.assertIn("s001:review-exhausted", self.notified())
        self.assertEqual(len(self.events("review-exhausted")), 1)

    def test_invalid_review_counts_against_review_loops(self):
        self.configure(levers="review_loops = 1\n")
        self.fake(REVIEW="invalid")
        self.open()
        st = self.drive(limit=8)
        self.assertEqual(st.name, "review-exhausted", story.render(st))
        self.assertIn("Verdict must be one of yes, no", st.detail)
        self.assertEqual(sum(m.startswith("story-reviewer") for m in self.modes()), 2)
        subjects = git(self.wt(), "log", "--format=%s").splitlines()
        self.assertEqual(sum(s.startswith("verify s001") for s in subjects), 1)

    # -- fixing ----------------------------------------------------------------------------------
    def test_report_then_code_after_a_no_is_still_fixing(self):
        self.configure(levers="review_loops = 5\n")
        self.fake(REVIEW="no")
        self.open()
        st = story.next_step(self.cfg, "s001")
        self.assertEqual((st.name, st.fix_mode), ("fixing", "fix-review"), story.render(st))
        wt = self.wt()
        write(wt / "docs/stories/s001/report.md", "## Delivered\nfix\n\nOutcome: done — fixed\n")
        git(wt, "add", "-A")
        git(wt, "commit", "--quiet", "-m", "report\n\nStory: s001\nAgent: story-implementer")
        self.assertEqual(story.state(self.cfg, "s001").name, "to-verify")
        write(wt / "src/app.txt", "v1\nlate fix\n")
        git(wt, "commit", "--quiet", "-am", "code\n\nStory: s001\nAgent: story-implementer")
        st = story.state(self.cfg, "s001")
        self.assertEqual((st.name, st.fix_mode), ("fixing", "fix-review"), story.render(st))

    def test_code_after_a_yes_is_implementing(self):
        self.open()
        self.drive()
        write(self.wt() / "src/app.txt", "v1\nlate\n")
        git(self.wt(), "commit", "--quiet", "-am", "late\n\nStory: s001\nAgent: story-implementer")
        self.assertEqual(story.state(self.cfg, "s001").name, "implementing")

    # -- sessions (§9.1, §9.3) and resumes -------------------------------------------------------
    def test_crashed_implementer_is_resumed_and_journaled(self):
        self.fake(IMPL="crash")
        self.open()
        self.assertEqual(self.events("resume"), [])
        st = story.next_step(self.cfg, "s001")
        self.assertEqual(st.name, "open")
        self.assertEqual(len(self.events("resume")), 1)
        self.assertEqual(self.modes(), ["story-implementer implement"] * 2)

    def test_live_session_is_not_doubled_and_a_stall_is_alerted(self):
        self.configure(levers="stall_minutes = 0\n")
        self.fake(IMPL="crash")
        self.open()
        self.fake(ALIVE="story-implementer")
        st = story.next_step(self.cfg, "s001")
        self.assertIn("session running: story-implementer", st.detail)
        self.assertEqual(len(self.modes()), 1)
        time.sleep(0.1)
        self.assertEqual(story.check_stall(self.cfg, "s001"), ["story-implementer"])
        story.check_stall(self.cfg, "s001")
        self.assertTrue(any(k.startswith("s001:stall:") for k in self.notified()))
        self.assertEqual(len(self.events("stall")), 1)

    def test_question_stops_as_blocked(self):
        self.fake(IMPL="question")
        self.open()
        self.assertEqual(self.drive().name, "blocked")

    def test_go_is_a_human_gesture(self):
        write(self.repo / "backlog/s001-sign-in.md", CARD.replace("spec: s001", "spec: s001\nshow_plan: true"))
        self.commit_all("show plan")
        git(self.repo, "push", "--quiet", "origin", "main")
        self.open()
        self.assertEqual(self.drive().name, "plan-ready")
        os.environ["DELIVERY_ROLE"] = "story-implementer"
        with self.assertRaises(core.DeliveryError) as ctx:
            story.next_step(self.cfg, "s001", go=True)
        self.assertEqual(ctx.exception.code, core.EXIT_REFUSED)

    # -- max_in_flight (§12.4: stopped stories do not count) ------------------------------------
    def test_max_in_flight(self):
        write(self.repo / "backlog/s002-lists.md", CARD.replace("s001", "s002"))
        self.commit_all("s002")
        git(self.repo, "push", "--quiet", "origin", "main")
        self.fake(IMPL="crash")
        self.open()
        with self.assertRaises(core.DeliveryError) as ctx:
            self.open("s002")
        self.assertEqual(ctx.exception.code, core.EXIT_PRECONDITION)
        self.assertIn("in flight: s001 : Sign in", ctx.exception.message)

    def test_a_stopped_story_does_not_count_in_flight(self):
        write(self.repo / "backlog/s002-lists.md", CARD.replace("s001", "s002"))
        self.commit_all("s002")
        git(self.repo, "push", "--quiet", "origin", "main")
        self.fake(IMPL="deferred")
        self.open()
        self.assertEqual(self.drive().name, "deferred")
        self.assertEqual(self.open("s002").name, "deferred")

    # -- integration check (§10) and authorship of the verdicts (§6) ----------------------------
    def test_gate_refusals(self):
        self.open()
        wt = self.drive().worktree
        write(wt / "backlog/s009-x.md", CARD.replace("s001", "s009"))
        write(wt / "backlog/s001-sign-in.md", CARD + "- one more line\n")
        write(wt / "docs/stories/s002/order.md", "x\n")
        own = wt / "docs/stories/s001"
        write(own / "report.md", (own / "report.md").read_text().replace("Outcome: done", "Outcome: blocked"))
        write(own / "review.md", (own / "review.md").read_text().replace("Verdict: yes", "Verdict: no"))
        write(own / "verification.md", (own / "verification.md").read_text() + "Evidence: nowhere/missing.txt\n")
        git(wt, "add", "-A")
        git(wt, "commit", "--quiet", "-m", "violations\n\nStory: s001\nAgent: story-implementer")
        problems = gate.check(story.Git(wt), "s001")
        for text in ("does not end with 'Outcome: done'", "verdict is 'no', expected 'yes'",
                     "changes an existing card", "not an anomaly to triage", "another story's folder",
                     "Evidence 'nowhere/missing.txt' is not in the tree",
                     "review.md: last committed with 'Agent: story-implementer', expected 'Agent: story-reviewer'",
                     "verification.md: last committed with 'Agent: story-implementer', expected 'Agent: engine'"):
            self.assertTrue(any(text in p for p in problems), (text, problems))
        order_commit = git(wt, "rev-list", "--reverse", "origin/main..HEAD").split()[0]
        problems = gate.check(story.Git(wt), "s001", base=order_commit)
        self.assertTrue(any("first commit of the branch must add" in p for p in problems), problems)

    def forge_verdicts(self, verification_agent, review_agent):
        """The implementer writes the verdicts itself, as if they were valid."""
        self.open(start=False)
        wt = self.wt()
        write(wt / "src/app.txt", "v1\nforged\n")
        git(wt, "commit", "--quiet", "-am", "code\n\nStory: s001\nAgent: story-implementer")
        tree = story.Git(wt).code_tree()
        own = wt / "docs/stories/s001"
        write(own / "report.md", "## Delivered\nall\n\nOutcome: done — all\n")
        write(own / "verification.md", f"Verdict: pass\nTree: {tree}\nCommand: true\nResult: ok\nBy: engine\n")
        git(wt, "add", "-A")
        git(wt, "commit", "--quiet", "-m", f"verdict\n\nStory: s001\nAgent: {verification_agent}")
        write(own / "review.md", f"Verdict: yes\nTree: {tree}\nCommand: true\nResult: ok\nBy: story-reviewer\n")
        git(wt, "add", "-A")
        git(wt, "commit", "--quiet", "-m", f"review\n\nStory: s001\nAgent: {review_agent}")
        return wt

    def test_verdicts_written_by_the_implementer_do_not_count(self):
        wt = self.forge_verdicts("story-implementer", "story-implementer")
        self.assertTrue((self.repo / ".delivery/run/verdicts.json").exists())  # created by story open
        self.assertEqual(story.state(self.cfg, "s001").name, "to-verify")
        problems = gate.check(story.Git(wt), "s001")
        self.assertTrue(any("expected 'Agent: engine'" in p for p in problems), problems)
        self.assertTrue(any("expected 'Agent: story-reviewer'" in p for p in problems), problems)

    def test_forged_trailers_do_not_pass_the_engine_registry(self):
        verify.register(self.repo, "s999", "verification", "0" * 40)
        self.forge_verdicts("engine", "story-reviewer")
        self.assertEqual(story.state(self.cfg, "s001").name, "to-verify")
        st = self.drive()
        self.assertEqual(st.name, "submitted", story.render(st))
        self.assertIn("story-reviewer loop 1", self.modes())

    # -- verification: port, UI tests, 0 test ----------------------------------------------------
    def test_verify_gives_the_port_and_counts_zero_tests_as_red(self):
        self.configure(commands='acceptance = "echo port={port} env=$DELIVERY_PORT grep={grep}; echo 0 passed"\n')
        self.open()
        port = ports.port(self.cfg, "s001")
        card = story._card(story.Git(self.repo), "s001", self.cfg)
        result = verify.verify(self.cfg, self.wt(), "s001", card)
        self.assertEqual(result.verdict, "fail")
        self.assertIn("acceptance exit 0, 0 tests", result.result)
        log = (self.wt() / "docs/stories/s001/work/verify.log").read_text()
        self.assertIn(f"port={port} env={port} grep=@s001", log)

    # -- forge: submitted, unreachable, merged with the branch deleted --------------------------
    def test_forge_submission_outage_and_merge(self):
        self.configure(forge="github")
        bin_dir = self.tmp / "bin"
        gh = write(bin_dir / "gh", FAKE_GH.format(python=sys.executable, state=str(self.tmp / "gh-state"),
                                                  calls=str(self.tmp / "gh-calls")))
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
        creates = lambda: (self.tmp / "gh-calls").read_text().count("pr create")
        self.open()
        st = story.next_step(self.cfg, "s001")
        self.assertEqual(st.name, "ready-to-submit", story.render(st))
        st = story.next_step(self.cfg, "s001")
        self.assertEqual(st.name, "submitted", story.render(st))
        self.assertIn(f"s001:submitted:{st.tree}", self.notified())
        self.assertIn("pr create --base main --head story/s001 --title s001 : Sign in (story/s001) --body-file",
                      (self.tmp / "gh-calls").read_text())
        (self.tmp / "gh-state").write_text("DOWN")
        st = story.state(self.cfg, "s001")
        self.assertEqual((st.name, st.engine_next), ("ready-to-submit", ""))
        self.assertIn("forge unreachable: retry", st.detail)
        story.scan(self.cfg)
        self.assertEqual(creates(), 1)
        (self.tmp / "gh-state").write_text("MERGED")
        git(self.repo, "push", "--quiet", "origin", "--delete", "story/s001")
        self.assertEqual(story.state(self.cfg, "s001").name, "merged")
        story.next_step(self.cfg, "s001")
        self.assertEqual(creates(), 1)
        self.assertEqual(git(self.repo, "ls-remote", "origin", "refs/heads/story/s001"), "")

    # -- names: '<id> : <short title>' (CONTRACTS.md §5) -------------------------------------------
    def test_status_commits_prompts_and_merge_name_the_story(self):
        self.open()
        st = self.drive()
        self.assertEqual(story.render(st).splitlines()[0], "s001 : Sign in — submitted")
        self.assertEqual(story.describe(self.cfg, "s001").splitlines()[0], "s001 : Sign in — submitted")
        subjects = git(self.wt(), "log", "--format=%s", "origin/main..HEAD").splitlines()
        self.assertEqual(subjects[-1], "order s001 : Sign in")
        self.assertIn("verify s001 : Sign in — pass", subjects)
        verification = (self.wt() / "docs/stories/s001/verification.md").read_text()
        self.assertTrue(verification.startswith("# Verification of s001 : Sign in\n"), verification)
        prompts = (self.wt() / "docs/stories/s001/work/fake-prompts").read_text().splitlines()
        self.assertEqual(prompts[0], "Story s001 : Sign in — read docs/stories/s001/order.md and carry it out. "
                                     "Mode: implement.")
        self.assertTrue(prompts[1].startswith("Story s001 : Sign in — review the change at code tree "), prompts)
        code, out = self.cli("gate", "s001")
        self.assertEqual((code, out.splitlines()[-1]), (0, "s001 : Sign in — integration check green"))
        story.merge(self.cfg, "s001")
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s"), "Merge story/s001 : Sign in")
        self.assertIn("s001", cards.merged_ids(story.Git(self.repo)))
        self.assertTrue(story.close(self.cfg, "s001").startswith("closed s001 : Sign in; work files removed"))
        self.assertEqual(story.render(story.state(self.cfg, "s001")).splitlines()[0], "s001 : Sign in — closed")

    def cli(self, *argv) -> tuple[int, str]:
        from deliveryctl import cli
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_notification_and_journal_name_the_story(self):
        self.configure(levers="verify_attempts = 0\n")
        self.fake(BREAK="always")
        self.open()
        err = io.StringIO()
        with redirect_stderr(err):
            story.next_step(self.cfg, "s001")
        self.assertIn("[notification] ⚠ todo — s001 : Sign in — borne atteinte — read ", err.getvalue())
        self.assertTrue(self.events("verify-exhausted")[0]["text"].startswith("s001 : Sign in — read "))

    def test_unknown_card_is_named_by_its_id(self):
        self.assertEqual(cards.label_of(story.Git(self.repo), "s999"), "s999")
        self.assertEqual(story.render(story.state(self.cfg, "s999")).splitlines()[0], "s999 — none")
        self.assertEqual(cards.label_of(story.Git(self.tmp), "s001"), "s001")      # not a repository
        self.assertEqual(cards.label_of(story.Git(self.repo), "s001"), "s001 : Sign in")

    def test_transcript_path(self):
        base = self.home / ".claude/projects"
        self.assertEqual(story.transcript_path("/tmp/projé-test", "abc"), base / "-tmp-proj--test/abc.jsonl")
        found = write(base / "-a-shortened-slug-1f2e/sid-1.jsonl", "{}\n")
        self.assertEqual(story.transcript_path("/a/very/long/path", "sid-1"), found)


if __name__ == "__main__":
    import unittest
    unittest.main()
