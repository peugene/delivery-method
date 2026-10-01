"""Plugin hooks: silent outside role sessions, block once without an Outcome line on the last
line, check the reviewer's verdict block, carry permission refusals to the journal once."""

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from support import ENGINE, ROOT, RepoCase, git, write

from deliveryctl import hooks, story
from deliveryctl.gate import story_of_branch
from deliveryctl.gitops import Git


def run_stop(payload, role=None, scope=None):
    env_backup = dict(os.environ)
    if role:
        os.environ["DELIVERY_ROLE"] = role
    else:
        os.environ.pop("DELIVERY_ROLE", None)
    if scope:
        os.environ["DELIVERY_STORY"] = scope
    sys_stdin = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = hooks.stop()
    finally:
        sys.stdin = sys_stdin
        os.environ.clear()
        os.environ.update(env_backup)
    return code, out.getvalue(), err.getvalue()


class StopHookTest(unittest.TestCase):
    def test_silent_outside_roles(self):
        self.assertEqual(run_stop({"last_assistant_message": "hello"})[:2], (0, ""))

    def test_blocks_once_without_outcome(self):
        code, out, _ = run_stop({"last_assistant_message": "I am done.", "stop_hook_active": False},
                                role="story-implementer")
        self.assertEqual(code, 0)
        reason = json.loads(out)["reason"]
        self.assertEqual(json.loads(out)["decision"], "block")
        self.assertIn("'Ends with'", reason)
        self.assertNotIn("deferred", reason)
        code, out, _ = run_stop({"last_assistant_message": "I am done.", "stop_hook_active": True},
                                role="story-implementer")
        self.assertEqual(out, "")

    def test_outcome_is_the_last_non_empty_line_only(self):
        self.assertEqual(hooks.last_outcome("text\nOutcome: done — ok\n\n").group(1), "done")
        self.assertEqual(hooks.last_outcome("Outcome: plan-ready — plan").group(1), "plan-ready")
        self.assertIsNone(hooks.last_outcome("the Outcome: line is missing"))
        self.assertIsNone(hooks.last_outcome("I will end with\nOutcome: done — ok\nonce tests pass."))

    def test_quoted_outcome_does_not_end_the_session(self):
        message = "s003 stopped. Its report ends with:\nOutcome: blocked — no tick endpoint\nI defer s003."
        with mock.patch.object(story, "detach_next") as detach:
            for role in ("technical-lead", "story-implementer"):
                code, out, err = run_stop({"last_assistant_message": message}, role=role, scope="s003")
                self.assertEqual(json.loads(out)["decision"], "block", role)
                self.assertNotIn("run terminé", err)
        detach.assert_not_called()

    def test_lead_ends_only_on_done_or_blocked(self):
        code, out, _ = run_stop({"last_assistant_message": "Outcome: question — which order?"},
                                role="technical-lead", scope="lead")
        self.assertEqual(json.loads(out)["decision"], "block")
        self.assertIn("Outcome: done", json.loads(out)["reason"])


class HookInRepoTest(RepoCase):
    def setUp(self):
        super().setUp()
        write(self.repo / "delivery.toml", 'repo_role = "impl"\nforge = "github"\n[commands]\ncheck = "true"\n')
        write(self.repo / ".gitignore", ".delivery/run/\n")
        self.commit_all("setup")

    def notified(self) -> dict:
        path = self.repo / ".delivery/run/notified.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def queue(self) -> list:
        path = self.home / ".local/state/delivery-method/journal-queue.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_lead_blocked_is_a_decision_and_done_is_the_end(self):
        _, out, err = run_stop({"session_id": "L1", "last_assistant_message": "…\nOutcome: blocked — no card"},
                               role="technical-lead", scope="lead")
        self.assertEqual(out, "")
        self.assertIn("⚠ todo — run arrêté", err)
        _, out, err = run_stop({"session_id": "L1", "last_assistant_message": "…\nOutcome: done — 3 merged"},
                               role="technical-lead", scope="lead")
        self.assertIn("⭐ todo — run terminé", err)
        self.assertEqual(len([k for k in self.notified() if k.startswith("run:L1:")]), 2)

    def test_lead_second_stop_without_outcome_alerts(self):
        payload = {"session_id": "L2", "transcript_path": "/x.jsonl", "last_assistant_message": "waiting"}
        _, out, _ = run_stop(dict(payload, stop_hook_active=False), role="technical-lead", scope="lead")
        self.assertEqual(json.loads(out)["decision"], "block")
        _, out, err = run_stop(dict(payload, stop_hook_active=True), role="technical-lead", scope="lead")
        self.assertEqual(out, "")
        self.assertIn("🚨 todo — run arrêté sans Outcome", err)
        self.assertEqual([e["category"] for e in self.queue()], ["stall"])

    def test_night_runner_does_not_notify(self):
        _, out, err = run_stop({"session_id": "N1", "last_assistant_message": "Outcome: done — 2 faults; anomalies a001"},
                               role="qualification-runner", scope="nightly-2026-01-01")
        self.assertEqual((out, err), ("", ""))
        self.assertEqual(self.notified(), {})
        _, _, err = run_stop({"session_id": "Q1", "last_assistant_message": "Outcome: done — 2 controls"},
                             role="qualification-runner", scope="0.1.0")
        self.assertIn("recette 0.1.0", err)

    def test_human_question_toast_once_per_message(self):
        payload = {"session_id": "H1", "cwd": str(self.repo),
                   "last_assistant_message": "Two options.\nOutcome: question — GO of the framing"}
        for _ in range(2):
            self.assertEqual(run_stop(payload)[:2], (0, ""))
        self.assertEqual(len(self.notified()), 1)
        quoted = dict(payload, session_id="H2", last_assistant_message="Outcome: question — x\nthen more")
        run_stop(quoted)
        self.assertEqual(len(self.notified()), 1)

    def review(self, verdict_block: str):
        path = self.repo / "docs/stories/s001/review.md"
        write(path, "## Findings\n1. none\n\n" + verdict_block)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "--quiet", "-m", "review")

    def test_reviewer_with_invalid_review_is_blocked_once(self):
        from deliveryctl.gitops import Git
        tree = Git(self.repo).code_tree()
        payload = {"session_id": "R1", "cwd": str(self.repo), "last_assistant_message": "Outcome: done — verdict yes"}
        with mock.patch.object(story, "detach_next") as detach:
            _, out, _ = run_stop(payload, role="story-reviewer", scope="s001")
            self.assertIn("review.md: it is not committed", json.loads(out)["reason"])
            self.review(f"Verdict: yes — minor notes only\nTree: {tree}\nCommand: true\nResult: ok\nBy: story-reviewer\n")
            _, out, _ = run_stop(payload, role="story-reviewer", scope="s001")
            self.assertIn("Verdict must be one of yes, no", json.loads(out)["reason"])
            self.assertIn(f"Tree: {tree}", json.loads(out)["reason"])
            self.review(f"Verdict: yes\nTree: {'0' * 40}\nCommand: true\nResult: ok\nBy: story-reviewer\n")
            _, out, _ = run_stop(payload, role="story-reviewer", scope="s001")
            self.assertIn("is not the current code tree", json.loads(out)["reason"])
            detach.assert_not_called()
            _, out, _ = run_stop(dict(payload, stop_hook_active=True), role="story-reviewer", scope="s001")
            self.assertEqual(out, "")
            self.assertEqual(detach.call_count, 1)
            self.review(f"Verdict: yes\nTree: {tree}\nCommand: true\nResult: ok\nBy: story-reviewer\n")
            _, out, _ = run_stop(payload, role="story-reviewer", scope="s001")
            self.assertEqual(out, "")
            self.assertEqual(detach.call_count, 2)

    def cloud_story_branch(self):
        """A branch built like the engine builds it: order.md alone in the first commit."""
        self.cloud_branch()
        git(self.repo, "push", "--quiet", "-u", "origin", "HEAD")

    def cloud_branch(self):
        git(self.repo, "push", "--quiet", "origin", "main")
        git(self.repo, "checkout", "--quiet", "-b", "claude/s001")
        write(self.repo / "docs/stories/s001/order.md", "order\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "--quiet", "-m", "order")

    def cloud_stop(self, last, active=False, cwd=None):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "true"}), \
                mock.patch.object(story, "detach_next") as detach:
            payload = {"session_id": "C1", "cwd": str(cwd or self.repo), "last_assistant_message": last,
                       "stop_hook_active": active}
            _, out, _ = run_stop(payload)
        detach.assert_not_called()
        return json.loads(out)["reason"] if out else ""

    def test_cloud_story_stop_blocks_once_then_lets_end(self):
        self.cloud_story_branch()
        self.assertIn("Outcome line", self.cloud_stop("done."))
        self.assertEqual(self.cloud_stop("done.", active=True), "")
        self.assertEqual(self.cloud_stop("Outcome: done — ok"), "")
        write(self.repo / "docs/stories/s001/report.md", "r\n")
        self.assertIn("Commit docs/stories/s001/report.md", self.cloud_stop("Outcome: done — ok"))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "--quiet", "-m", "report")
        self.assertIn("git push -u origin HEAD", self.cloud_stop("Outcome: done — ok"))
        self.assertEqual(self.cloud_stop("Outcome: done — ok", active=True), "")
        git(self.repo, "push", "--quiet")
        self.assertEqual(self.cloud_stop("Outcome: done — ok"), "")
        self.assertFalse(self.notified())

    def story_only_clone(self):
        """A cloud clone of the story branch alone: no origin/HEAD, no main."""
        git(self.repo, "checkout", "--quiet", "-b", "story/s001")
        write(self.repo / "docs/stories/s001/order.md", "order\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "--quiet", "-m", "order s001", "-m", "Story: s001\nAgent: engine")
        git(self.repo, "push", "--quiet", "origin", "story/s001")
        clone = self.tmp / "cloud-clone"
        git(self.tmp, "clone", "--quiet", "--single-branch", "--branch", "story/s001", str(self.origin), str(clone))
        return clone

    def test_story_of_a_clone_without_the_target_branch(self):
        clone = self.story_only_clone()
        self.assertIsNone(Git(clone).rev("main"))
        self.assertEqual(story_of_branch(Git(clone)), "s001")
        self.assertIn("Outcome line", self.cloud_stop("done.", cwd=clone))
        self.assertEqual(self.cloud_stop("done.", active=True, cwd=clone), "")

    def test_no_order_commit_means_no_story_without_the_target_branch(self):
        clone = self.story_only_clone()
        write(clone / "x.txt", "x\n")
        git(clone, "add", "-A")
        git(clone, "commit", "--quiet", "-m", "order s002", "-m", "Agent: engine")   # not the order file
        git(clone, "commit", "--quiet", "--amend", "-m", "order s003")               # no engine trailer
        git(clone, "checkout", "--quiet", "--orphan", "free")
        git(clone, "commit", "--quiet", "--allow-empty", "-m", "nothing")
        self.assertIsNone(story_of_branch(Git(clone)))
        self.assertEqual(self.cloud_stop("no outcome", cwd=clone), "")

    def test_cloud_branch_without_upstream_is_blocked(self):
        self.cloud_branch()
        self.assertIn("git push -u origin HEAD", self.cloud_stop("Outcome: done — ok"))

    def test_cloud_session_outside_a_story_does_not_notify(self):
        git(self.repo, "checkout", "--quiet", "-b", "claude/free")
        self.assertEqual(self.cloud_stop("Two options.\nOutcome: question — GO"), "")
        self.assertFalse(self.notified())
        self.assertEqual(self.cloud_stop("no outcome"), "")

    def test_cloud_session_start_reminds_the_story(self):
        self.cloud_story_branch()
        for source in ("startup", "resume"):
            out = self.session_start(source, CLAUDE_CODE_REMOTE="true")
            self.assertIn("story-implementer of story s001", out)
            self.assertIn("docs/stories/s001/order.md", out)
        self.assertIn("Context was compacted", self.session_start("compact", CLAUDE_CODE_REMOTE="true", DELIVERY_ROLE="story-implementer", DELIVERY_STORY="s001"))
        self.assertEqual(self.session_start("clear", CLAUDE_CODE_REMOTE="true"), "")

    def transcript(self, denied_commands):
        lines = []
        for n, command in enumerate(denied_commands):
            lines.append({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": f"t{n}", "name": "Bash", "input": {"command": command}}]}})
            lines.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": f"t{n}", "is_error": True,
                 "content": "Permission to use Bash has been denied because Claude Code is running in don't ask mode."}]}})
        lines.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "ok", "is_error": True, "content": "exit 1"}]}})
        path = self.tmp / "transcript.jsonl"
        path.write_text("".join(json.dumps(line) + "\n" for line in lines))
        return path

    def test_refusals_are_journaled_once(self):
        write(self.repo / ".delivery/run/sessions/s001.json",
              json.dumps({"story-implementer": {"session_id": "S1", "log": "x"}}))
        path = self.transcript(["ls /home", "rm -rf work"])
        payload = {"session_id": "S1", "transcript_path": str(path), "last_assistant_message": "Outcome: done — ok"}
        with mock.patch.object(story, "detach_next"):
            run_stop(payload, role="story-implementer", scope="s001")
            run_stop(payload, role="story-implementer", scope="s001")
            refusals = [e for e in self.queue() if e["category"] == "refusal"]
            self.assertEqual(len(refusals), 1)
            self.assertIn("2 refusal(s): Bash: ls /home | Bash: rm -rf work", refusals[0]["text"])
            self.assertEqual(refusals[0]["story"], "s001")
            self.transcript(["ls /home", "rm -rf work", "git push"])
            run_stop(payload, role="story-implementer", scope="s001")
        refusals = [e for e in self.queue() if e["category"] == "refusal"]
        self.assertEqual(len(refusals), 2)
        self.assertIn("1 refusal(s): Bash: git push", refusals[1]["text"])
        session = json.loads((self.repo / ".delivery/run/sessions/s001.json").read_text())["story-implementer"]
        self.assertTrue(session["denials_recorded"])

    def session_start(self, source: str, **env) -> str:
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), mock.patch("sys.stdin", io.StringIO(json.dumps({"source": source, "cwd": str(self.repo)}))), \
                redirect_stdout(out):
            self.assertEqual(hooks.session_start(), 0)
        return out.getvalue()

    def test_session_start_puts_the_project_copy_on_the_path_at_every_start(self):
        write(self.repo / ".delivery" / "deliveryctl", "#!/bin/sh\n")
        env_file = self.tmp / "claude-env.sh"
        for source in ("startup", "resume", "clear", "compact"):
            out = self.session_start(source, CLAUDE_ENV_FILE=str(env_file), CLAUDE_PROJECT_DIR=str(self.repo))
            self.assertEqual(out, "")                  # no role: nothing to say
        line = f'export PATH="{self.repo}/.delivery:$PATH"\n'
        self.assertEqual(env_file.read_text(), line * 4)
        self.assertEqual(self.session_start("startup"), "")      # no env file: silent

    def test_session_start_reminds_a_role_after_a_compaction_only(self):
        env = {"DELIVERY_ROLE": "story-implementer", "DELIVERY_STORY": "s001"}
        self.assertEqual(self.session_start("startup", **env), "")
        out = self.session_start("compact", **env)
        self.assertIn("Context was compacted", out)
        self.assertIn("docs/stories/s001/order.md", out)
        self.assertEqual([e["category"] for e in self.queue()], ["compact"])

    def test_session_start_stays_quiet_on_an_unwritable_env_file(self):
        out = self.session_start("startup", CLAUDE_ENV_FILE=str(self.tmp / "no" / "dir" / "env"),
                                 CLAUDE_PROJECT_DIR=str(self.repo))
        self.assertEqual(out, "")


class OldPythonTest(unittest.TestCase):
    """Outside role sessions, the hooks stay silent when the engine cannot run (Python < 3.11)."""

    def test_hook_without_tomllib_is_silent(self):
        code = ("import sys; sys.modules['tomllib'] = None; sys.path.insert(0, sys.argv[1]); "
                "from deliveryctl.cli import main; sys.exit(main(['hook', 'stop']))")
        env = {k: v for k, v in os.environ.items() if k not in ("DELIVERY_ROLE", "CLAUDE_CODE_REMOTE")}
        for message in ("hello", "Two options.\nOutcome: question — GO"):
            proc = subprocess.run([sys.executable, "-c", code, str(ENGINE)], text=True, capture_output=True,
                                  input=json.dumps({"last_assistant_message": message}), env=env)
            self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))

    def test_launcher_is_silent_for_hooks_with_an_old_python(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "python3"
            fake.write_text("#!/bin/sh\necho 'Python 3.10' >&2\nexit 1\n")
            fake.chmod(0o755)
            env = dict(os.environ, PATH=f"{tmp}:{os.environ['PATH']}")
            proc = subprocess.run([str(ROOT / "bin" / "deliveryctl"), "hook", "stop"], text=True,
                                  capture_output=True, input="{}", env=env, cwd=tmp)
            self.assertEqual((proc.returncode, proc.stdout, proc.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
