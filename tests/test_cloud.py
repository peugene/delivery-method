"""The story-implementer as a Claude Code cloud session: the setting, the launch through a
pseudo-terminal after the push of the story branch, the cloud window and the registry it shares
with the other windows, `story status` and `doctor`. A fake `claude` stands for the real one."""

import io
import json
import os
import sys
import time
import tomllib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from support import RepoCase, git, sh, write
from test_story import CARD, ORDER

from deliveryctl import config, doctor, journal, roles, story
from deliveryctl.cli import main as cli_main
from deliveryctl.core import EXIT_ERROR, EXIT_PRECONDITION, EXIT_TOOL, DeliveryError
from deliveryctl.window import cloud, owner
from deliveryctl.window.base import Window

# Fails like the real `claude --cloud` when its output is not a terminal, else records its
# arguments and prints the three lines of a created session.
FAKE_CLAUDE = r'''#!PYTHON
import json, os, sys
from pathlib import Path
home = Path(os.environ["FAKE_CLAUDE_DIR"])
if sys.argv[1:3] == ["auth", "status"]:
    print(os.environ.get("FAKE_CLAUDE_AUTH", '{"loggedIn": true, "authMethod": "claude.ai"}'))
    sys.exit(0)
if not (sys.stdin.isatty() and sys.stdout.isatty()):
    print("Error: --cloud requires an interactive terminal.", file=sys.stderr)
    sys.exit(1)
with (home / "calls").open("a") as fh:
    fh.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "env": sorted(os.environ)}) + "\n")
mode = os.environ.get("FAKE_CLAUDE_MODE", "")
if mode == "fail":
    print("Error: no cloud environment")
    sys.exit(1)
if mode == "silent":
    print("Created nothing")
    sys.exit(0)
print("\033[1mCreated cloud session: Sign in\033[0m")
print("View: https://claude.ai/code/session_01ABC?from=cli&m=0")
print("Resume with: claude --teleport session_01ABC")
'''


class CloudCase(RepoCase):
    def setUp(self):
        super().setUp()
        os.environ["DELIVERY_FAKE_WINDOW"] = "1"
        home = self.tmp / "claude"
        tool = write(home / "bin" / "claude", FAKE_CLAUDE.replace("PYTHON", sys.executable, 1))
        tool.chmod(0o755)
        os.environ["FAKE_CLAUDE_DIR"] = str(home)
        os.environ["PATH"] = f"{home / 'bin'}{os.pathsep}{os.environ['PATH']}"
        self.claude_dir = home
        write(self.repo / "backlog/s001-sign-in.md", CARD)
        write(self.repo / ".gitignore", ".delivery/run/\ndocs/stories/*/work/\n")
        self.configure()

    def configure(self, top="", levers=""):
        write(self.repo / "delivery.toml",
              f'repo_role = "impl"\nforge = "github"\n{top}[commands]\ncheck = "true"\n[levers]\n{levers}')
        self.commit_all("settings")
        git(self.repo, "push", "--quiet", "origin", "main")
        self.cfg = config.load(self.repo)

    def calls(self) -> list[dict]:
        path = self.claude_dir / "calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def open(self, start=True):
        order = story.prepare(self.cfg, "s001")
        base = git(self.repo, "rev-parse", "origin/main")
        order.write_text(ORDER.replace("{base}", base))
        return story.open_story(self.cfg, "s001", start=start)

    def entry(self) -> dict:
        return Window(self.repo).session("s001", "story-implementer")

    def wt(self) -> Path:
        return story.Git(self.repo).worktree_for("story/s001")


class ImplementerSettingTest(RepoCase):
    def load(self, text):
        return config.parse(tomllib.loads(text), self.repo)

    def test_default_follows_the_forge(self):
        self.assertEqual(self.load('repo_role = "impl"\nforge = "github"\n').implementer, "cloud")
        self.assertEqual(self.load('repo_role = "impl"\nforge = "gitlab"\n').implementer, "local")

    def test_written_value_wins_and_cloud_needs_github(self):
        self.assertEqual(self.load('repo_role = "impl"\nforge = "github"\nimplementer = "local"\n').implementer, "local")
        self.assertEqual(self.load('repo_role = "impl"\nforge = "gitlab"\nimplementer = "local"\n').implementer, "local")
        with self.assertRaises(DeliveryError) as ctx:
            self.load('repo_role = "impl"\nforge = "gitlab"\nimplementer = "cloud"\n')
        self.assertEqual(ctx.exception.code, EXIT_ERROR)
        self.assertIn("GitHub only", ctx.exception.message)
        with self.assertRaises(DeliveryError):
            self.load('repo_role = "impl"\nforge = "github"\nimplementer = "remote"\n')


class CloudLaunchTest(CloudCase):
    def test_push_then_launch_through_a_terminal_with_the_expected_arguments(self):
        self.open()
        wt = self.wt()
        remote = git(self.repo, "ls-remote", "origin", "refs/heads/story/s001").split()[0]
        self.assertEqual(remote, git(wt, "rev-parse", "HEAD"))      # pushed before the launch
        self.assertEqual(git(wt, "rev-parse", "--abbrev-ref", "story/s001@{upstream}"), "origin/story/s001")
        (call,) = self.calls()                                      # the fake refuses a pipe: this ran in a terminal
        argv = call["argv"]
        self.assertEqual(Path(call["cwd"]).resolve(), wt.resolve())
        self.assertEqual(argv[0], "--cloud")
        self.assertEqual(argv[1], (
            "You are the story-implementer of this repository: read .claude/agents/story-implementer.md "
            "and follow it as your instructions. Story s001 : Sign in — read docs/stories/s001/order.md and "
            "carry it out. Mode: implement. Where: cloud — use port 31001 wherever DELIVERY_PORT or "
            "{port} is asked."))
        self.assertEqual(argv[2:], ["--model", "sonnet", "--effort", "medium"])
        for flag in ("--agent", "--settings", "--permission-mode", "--setting-sources", "--session-id"):
            self.assertNotIn(flag, argv)
        for key in ("DELIVERY_ROLE", "DELIVERY_STORY", "DELIVERY_PORT"):
            self.assertNotIn(key, call["env"])

    def test_model_and_effort_come_from_the_agent_file(self):
        write(self.repo / ".claude/agents/story-implementer.md",
              "---\nname: story-implementer\nmodel: opus\neffort: high\n---\n")
        self.commit_all("agent")
        git(self.repo, "push", "--quiet", "origin", "main")
        self.open()
        self.assertEqual(self.calls()[0]["argv"][2:], ["--model", "opus", "--effort", "high"])

    def test_registry_entry_and_liveness(self):
        self.open()
        info = self.entry()
        self.assertEqual(info["window"], "cloud")
        self.assertEqual(info["session_id"], "session_01ABC")
        self.assertEqual(info["url"], "https://claude.ai/code/session_01ABC")
        self.assertEqual(info["head"], git(self.wt(), "rev-parse", "HEAD"))
        self.assertTrue(info["pushed_at"])
        self.assertTrue(info["step"].startswith("implement@"))
        # the machine window (fake) says nothing lives; the window that owns the entry is asked
        self.assertIs(owner(self.repo, info).role_alive("s001", "story-implementer"), True)
        self.assertEqual(story._alive(self.cfg, "s001"), ["story-implementer"])
        st = story.next_step(self.cfg, "s001")
        self.assertIn("session running: story-implementer", st.detail)
        self.assertEqual(len(self.calls()), 1)                      # never launched twice
        reg = Window(self.repo).sessions("s001")
        reg["story-implementer"]["ended"] = "2026-01-01T00:00:00Z"
        write(self.repo / ".delivery/run/sessions/s001.json", json.dumps(reg))
        self.assertEqual(story._alive(self.cfg, "s001"), [])

    def test_stop_does_nothing(self):
        self.open()
        cloud.CloudWindow(self.repo).stop_role("s001", "story-implementer")
        self.assertEqual(story._alive(self.cfg, "s001"), ["story-implementer"])

    def test_a_diverged_remote_branch_fails_before_the_launch(self):
        other = self.tmp / "other"
        git(self.tmp, "clone", "--quiet", str(self.origin), str(other))
        git(other, "checkout", "--quiet", "-b", "story/s001")
        write(other / "elsewhere.txt", "x\n")
        git(other, "add", "-A")
        git(other, "commit", "--quiet", "-m", "elsewhere")
        git(other, "push", "--quiet", "origin", "story/s001")
        with self.assertRaises(DeliveryError) as ctx:
            self.open()
        self.assertEqual(ctx.exception.code, EXIT_TOOL)
        self.assertIn("rejected", ctx.exception.message)
        self.assertEqual(self.calls(), [])
        self.assertIsNone(self.entry())

    def failed_launch(self, mode, text):
        os.environ["FAKE_CLAUDE_MODE"] = mode
        with self.assertRaises(DeliveryError) as ctx:
            self.open()
        self.assertEqual(ctx.exception.code, EXIT_TOOL)
        self.assertIn(text, ctx.exception.message)
        self.assertIsNone(self.entry())

    def test_a_non_zero_exit_names_the_output(self):
        self.failed_launch("fail", "no cloud environment")

    def test_no_view_line_is_a_failure(self):
        self.failed_launch("silent", "no 'View:' line")

    def test_local_keeps_todays_launch(self):
        self.configure(top='implementer = "local"\n')
        os.environ["DELIVERY_FAKE_AGENT"] = str(Path(__file__).resolve().parent / "e2e" / "fake_agent.py")
        self.open()
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.entry()["window"], "fake")
        self.assertEqual(git(self.repo, "ls-remote", "origin", "refs/heads/story/s001"), "")

    def test_the_timeout_ends_the_command(self):
        with self.assertRaises(DeliveryError) as ctx:
            cloud.run_in_terminal(["sleep", "30"], str(self.repo), dict(os.environ), 1)
        self.assertEqual(ctx.exception.code, EXIT_TOOL)
        self.assertIn("timeout after 1s", ctx.exception.message)

    def test_view_line_parsing(self):
        self.assertEqual(cloud.parse_view("x\nView: https://claude.ai/code/session_9?from=cli&m=0\n"),
                         ("session_9", "https://claude.ai/code/session_9"))
        self.assertIsNone(cloud.parse_view("Resume with: claude --teleport session_9"))

    def test_launch_needs_the_project_agent(self):
        wt = self.tmp / "bare"
        wt.mkdir()
        with self.assertRaises(DeliveryError) as ctx:
            roles.cloud_launch(self.cfg, wt, "s001", "go")
        self.assertIn("deliveryctl init --upgrade", ctx.exception.message)


class CloudStatusTest(CloudCase):
    def test_status_shows_the_url(self):
        self.open()
        self.assertIn("story-implementer in the cloud: https://claude.ai/code/session_01ABC",
                      story.describe(self.cfg, "s001"))
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(cli_main(["story", "status", "s001"]), 0)
        self.assertIn("https://claude.ai/code/session_01ABC", out.getvalue())


class CloudDoctorTest(CloudCase):
    def doctor(self, **env):
        os.environ.update(env)
        git(self.repo, "remote", "set-url", "origin", env.pop("ORIGIN", None) or "git@github.com:acme/todo.git")
        out = io.StringIO()
        with redirect_stdout(out):
            doctor.main([])
        return out.getvalue()

    def test_ready(self):
        out = self.doctor()
        self.assertIn("ok: claude logged in with claude.ai", out)
        self.assertNotIn("warn: implementer = cloud", out)
        self.assertIn("note: implementer = cloud: cloud sessions run in the default environment chosen by /remote-env", out)

    def test_not_logged_in_or_wrong_method(self):
        for auth in ('{"loggedIn": false}', '{"loggedIn": true, "authMethod": "api_key"}', "not json"):
            with self.subTest(auth=auth):
                out = self.doctor(FAKE_CLAUDE_AUTH=auth)
                self.assertIn("warn: implementer = cloud needs", out)
                self.assertIn("claude auth login", out)

    def test_origin_must_be_on_github(self):
        os.environ["FAKE_CLAUDE_AUTH"] = '{"loggedIn": true, "authMethod": "claude.ai"}'
        git(self.repo, "remote", "set-url", "origin", "https://gitlab.com/acme/todo.git")
        out = io.StringIO()
        with redirect_stdout(out):
            doctor.main([])
        self.assertIn("warn: implementer = cloud: origin (https://gitlab.com/acme/todo.git) is not on github.com", out.getvalue())

    def test_local_says_nothing(self):
        self.configure(top='implementer = "local"\n')
        self.assertNotIn("implementer = cloud", self.doctor())


SESSION = "https://claude.ai/code/session_01ABC"


class CloudRetrievalCase(CloudCase):
    """The cloud session is played by a second clone pushing `claude/<slug>` branches."""

    def setUp(self):
        super().setUp()
        self.other = self.tmp / "cloud-clone"
        self.open()
        git(self.tmp, "clone", "--quiet", str(self.origin), str(self.other))
        git(self.other, "config", "user.email", "cloud@example.test")
        git(self.other, "config", "user.name", "cloud")
        self.start = self.entry()["head"]

    def push_commit(self, files, branch="claude/work-1", session=SESSION, trailers=None, base=None,
                    message="implement"):
        """One commit of the session on `branch`, created from `base` (the pushed story)."""
        git(self.other, "fetch", "--quiet", "origin")
        if base or not git(self.other, "branch", "--list", branch):
            git(self.other, "checkout", "--quiet", "-B", branch, base or "origin/story/s001")
        else:
            git(self.other, "checkout", "--quiet", branch)
        for path, text in files.items():
            write(self.other / path, text)
        git(self.other, "add", "-A")
        trailers = ["Story: s001", "Agent: story-implementer", f"Claude-Session: {session}"] if trailers is None else trailers
        git(self.other, "commit", "--quiet", "-m", message + "\n\n" + "\n".join(trailers))
        git(self.other, "push", "--quiet", "origin", f"{branch}:{branch}")
        return git(self.other, "rev-parse", "HEAD")

    def pull(self, age=True):
        """One retrieval; `age` makes the 60-second limit pass first."""
        if age:
            info = self.entry()
            info["fetched_at"] = 0
            story._save_entry(self.cfg, "s001", info)
        story.pull_cloud(self.cfg, "s001")

    def head(self):
        return git(self.wt(), "rev-parse", "HEAD")

    def remote(self, ref):
        return git(self.repo, "ls-remote", "origin", f"refs/heads/{ref}")

    def notified(self):
        return json.loads((self.repo / ".delivery/run/notified.json").read_text())

    def events(self, category):
        path = journal.queue_path()
        lines = path.read_text().splitlines() if path.exists() else []
        return [e for e in map(json.loads, filter(str.strip, lines)) if e["category"] == category]

    REPORT = "## Delivered\nx\n\nOutcome: done — all delivered\n"


class CloudAcceptedTest(CloudRetrievalCase):
    def test_commits_fast_forward_the_story_and_the_branch_is_deleted(self):
        tip = self.push_commit({"src/app.txt": "line\n"})
        self.pull()
        self.assertEqual(self.head(), tip)
        self.assertEqual(self.remote("claude/work-1"), "")
        info = self.entry()
        self.assertEqual(info["head"], tip)
        self.assertTrue(info["last_commit_at"])
        self.assertNotIn("ended", info)            # no Outcome yet: the session goes on
        self.assertEqual(story.state(self.cfg, "s001").name, "implementing")

    def test_a_fresh_outcome_ends_the_session_and_leads_to_the_verification(self):
        self.push_commit({"src/app.txt": "line\n", "docs/stories/s001/report.md": self.REPORT})
        self.pull()
        self.assertTrue(self.entry()["ended"])
        self.assertEqual(story.state(self.cfg, "s001").name, "to-verify")
        self.assertEqual(story._alive(self.cfg, "s001"), [])
        self.assertEqual(len(self.calls()), 1)     # the story chains on, no second implementer

    def test_the_most_advanced_branch_wins_and_the_story_branch_counts(self):
        self.push_commit({"a.txt": "1\n"}, branch="claude/short")
        tip = self.push_commit({"a.txt": "1\n"}, branch="claude/long")
        tip = self.push_commit({"b.txt": "2\n"}, branch="claude/long")
        self.pull()
        self.assertEqual(self.head(), tip)
        self.assertEqual(self.remote("claude/long"), "")
        self.assertNotEqual(self.remote("claude/short"), "")

    def test_later_commits_on_the_same_branch_are_taken_in_turn(self):
        self.push_commit({"a.txt": "1\n"})
        self.pull()
        tip = self.push_commit({"b.txt": "2\n"}, base=self.head())
        self.pull()
        self.assertEqual(self.head(), tip)

    def test_an_anomaly_card_to_triage_is_accepted(self):
        card = "---\nid: x001\nkind: anomaly\ntitle: Odd\nstatus: to-triage\n---\n## Objective\nodd\n"
        tip = self.push_commit({"backlog/x001-odd.md": card})
        self.pull()
        self.assertEqual(self.head(), tip)

    def test_a_dirty_working_copy_holds_the_commits_until_it_is_clean(self):
        tip = self.push_commit({"src/app.txt": "line\n"})
        write(self.wt() / "stray.txt", "x\n")
        self.pull()
        self.assertNotEqual(self.head(), tip)
        self.assertIn("retried at the next sweep", story.state(self.cfg, "s001").detail)
        self.assertNotEqual(self.remote("claude/work-1"), "")
        (self.wt() / "stray.txt").unlink()
        self.pull()
        self.assertEqual(self.head(), tip)
        self.assertNotIn("retried", story.state(self.cfg, "s001").detail)


class CloudIgnoredTest(CloudRetrievalCase):
    def test_another_session_is_ignored(self):
        self.push_commit({"a.txt": "1\n"}, session="https://claude.ai/code/session_OTHER")
        self.pull()
        self.assertEqual(self.head(), self.start)
        self.assertNotIn("ended", self.entry())
        self.assertEqual(story.state(self.cfg, "s001").name, "open")

    def test_a_branch_with_one_foreign_commit_is_ignored(self):
        self.push_commit({"a.txt": "1\n"})
        self.push_commit({"b.txt": "2\n"}, session="https://claude.ai/code/session_OTHER")
        self.pull()
        self.assertEqual(self.head(), self.start)
        self.assertNotIn("rejected", self.entry())

    def test_a_branch_not_descending_from_the_head_is_ignored(self):
        git(self.other, "checkout", "--quiet", "-B", "claude/elsewhere", "origin/main")
        self.push_commit({"a.txt": "1\n"}, branch="claude/elsewhere", base="origin/main")
        self.pull()
        self.assertEqual(self.head(), self.start)
        self.assertNotIn("ended", self.entry())

    def test_a_cloud_free_story_is_left_alone(self):
        info = self.entry()
        info["window"] = "fake"
        story._save_entry(self.cfg, "s001", info)
        self.push_commit({"a.txt": "1\n"})
        self.pull()
        self.assertEqual(self.head(), self.start)


class CloudRefusedTest(CloudRetrievalCase):
    def refused(self, text, **kwargs):
        self.push_commit(**kwargs)
        self.pull()
        info = self.entry()
        self.assertEqual(self.head(), self.start)               # never fast-forwarded
        self.assertTrue(info["ended"])
        self.assertTrue(any(text in problem for problem in info["rejected"]), info["rejected"])
        st = story.state(self.cfg, "s001")
        self.assertEqual(st.name, "blocked")
        self.assertIn(text, st.detail)
        self.assertIn("deliveryctl story next s001 --relaunch", st.human_next)
        self.assertIn("origin/claude/work-1", st.human_next)
        keys = [k for k in self.notified() if k.startswith("s001:cloud-refused:")]
        self.assertEqual(len(keys), 1)
        (event,) = self.events("refusal")
        self.assertEqual(event["evidence"], f"origin/claude/work-1 — {SESSION}")
        story.next_step(self.cfg, "s001")                       # one notification, one event, no launch
        self.pull()
        self.assertEqual(len([k for k in self.notified() if "cloud-refused" in k or "blocked" in k]), 1)
        self.assertEqual(len(self.events("refusal")), 1)
        self.assertEqual(len(self.calls()), 1)
        self.assertNotEqual(self.remote("claude/work-1"), "")   # kept for inspection

    def test_a_verification_written_by_the_implementer(self):
        self.refused("verification.md", files={"docs/stories/s001/verification.md": "x\n"})

    def test_a_review_written_by_the_implementer(self):
        self.refused("review.md", files={"docs/stories/s001/review.md": "x\n"})

    def test_a_protected_path(self):
        self.refused("protected path: .claude/settings.json", files={".claude/settings.json": "{}\n"})

    def test_another_story_folder(self):
        self.refused("another story's folder", files={"docs/stories/s002/report.md": "x\n"})

    def test_a_change_to_a_backlog_card(self):
        self.refused("backlog/s001-sign-in.md", files={"backlog/s001-sign-in.md": CARD.replace("ready", "done")})

    def test_a_missing_story_trailer(self):
        self.refused("lacks the trailers", files={"a.txt": "1\n"},
                     trailers=["Agent: story-implementer", f"Claude-Session: {SESSION}"])

    def test_a_missing_agent_trailer(self):
        self.refused("lacks the trailers", files={"a.txt": "1\n"},
                     trailers=["Story: s001", f"Claude-Session: {SESSION}"])

    def test_another_agent_trailer(self):
        self.refused("lacks the trailers", files={"a.txt": "1\n"},
                     trailers=["Story: s001", "Agent: story-reviewer", f"Claude-Session: {SESSION}"])

    def test_a_merge_commit(self):
        self.push_commit({"a.txt": "1\n"})
        git(self.other, "checkout", "--quiet", "-B", "side", "origin/story/s001")
        write(self.other / "side.txt", "s\n")
        git(self.other, "add", "-A")
        git(self.other, "commit", "--quiet", "-m",
            f"side\n\nStory: s001\nAgent: story-implementer\nClaude-Session: {SESSION}")
        git(self.other, "checkout", "--quiet", "claude/work-1")
        git(self.other, "merge", "--quiet", "--no-ff", "side", "-m",
            f"merge\n\nStory: s001\nAgent: story-implementer\nClaude-Session: {SESSION}")
        git(self.other, "push", "--quiet", "origin", "claude/work-1:claude/work-1")
        self.pull()
        self.assertEqual(self.head(), self.start)
        self.assertTrue(any("merge commit" in p for p in self.entry()["rejected"]))

    def test_a_tip_not_descending_from_the_local_head(self):
        self.push_commit({"a.txt": "1\n"})
        write(self.wt() / "local.txt", "x\n")
        git(self.wt(), "add", "-A")
        git(self.wt(), "commit", "--quiet", "-m", "local")
        self.pull()
        self.assertTrue(any("does not descend" in p for p in self.entry()["rejected"]))

    def test_relaunch_after_a_refusal(self):
        self.push_commit({"docs/stories/s001/verification.md": "x\n"})
        self.pull()
        self.assertEqual(story.state(self.cfg, "s001").name, "blocked")
        st = story.relaunch(self.cfg, "s001")
        self.assertEqual(len(self.calls()), 2)
        self.assertNotIn("rejected", self.entry())
        self.assertNotIn("ended", self.entry())
        self.assertEqual(self.entry()["head"], self.head())
        self.assertNotEqual(st.name, "blocked")


class CloudFetchLimitTest(CloudRetrievalCase):
    def test_one_fetch_per_minute(self):
        self.pull()
        tip = self.push_commit({"a.txt": "1\n"})
        self.pull(age=False)
        self.assertEqual(self.head(), self.start)               # inside the limit: not even fetched
        self.assertTrue(self.entry()["fetched_at"] > 0)
        info = self.entry()
        info["fetched_at"] -= 61
        story._save_entry(self.cfg, "s001", info)
        story.pull_cloud(self.cfg, "s001")
        self.assertEqual(self.head(), tip)

    def test_every_sweep_retrieves(self):
        tip = self.push_commit({"a.txt": "1\n"})
        story.scan(self.cfg)
        self.assertEqual(self.head(), tip)
        tip = self.push_commit({"b.txt": "2\n"}, base=tip)
        self.pull()
        story.next_step(self.cfg, "s001")
        self.assertEqual(self.head(), tip)
        self.assertIn("a.txt", git(self.wt(), "ls-files"))

    def test_status_and_wait_retrieve(self):
        tip = self.push_commit({"docs/stories/s001/report.md": self.REPORT})
        text = story.describe(self.cfg, "s001")
        self.assertEqual(self.head(), tip)
        self.assertIn("to-verify", text)

    def test_a_network_error_is_shown_and_does_not_stop_the_sweep(self):
        git(self.repo, "remote", "set-url", "origin", str(self.tmp / "nowhere.git"))
        err = io.StringIO()
        with redirect_stderr(err):
            self.pull()
            story.scan(self.cfg)
        self.assertIn("cloud commits", err.getvalue())
        self.assertEqual(self.head(), self.start)


class CloudStallTest(CloudRetrievalCase):
    def stale(self, **fields):
        info = self.entry()
        info.update(fields)
        story._save_entry(self.cfg, "s001", info)

    def test_a_session_without_progress_is_alerted_once(self):
        self.configure(levers="stall_minutes = 30\n")
        self.assertEqual(story.check_stall(self.cfg, "s001"), [])
        self.stale(pushed_at="2020-01-01T00:00:00Z")
        self.assertEqual(story.check_stall(self.cfg, "s001"), ["story-implementer"])
        story.check_stall(self.cfg, "s001")
        keys = [k for k in self.notified() if k.startswith("s001:stall:")]
        self.assertEqual(len(keys), 1)
        (event,) = self.events("stall")
        self.assertEqual(event["evidence"], SESSION)

    def test_a_retrieved_commit_is_progress(self):
        self.configure(levers="stall_minutes = 30\n")
        self.stale(pushed_at="2020-01-01T00:00:00Z", last_commit_at=story._iso(time.time()))
        self.assertEqual(story.check_stall(self.cfg, "s001"), [])

    def test_an_ended_session_does_not_stall(self):
        self.stale(pushed_at="2020-01-01T00:00:00Z", ended="2020-01-02T00:00:00Z")
        self.assertEqual(story.check_stall(self.cfg, "s001"), [])

    def test_no_second_implementer_while_the_session_has_no_end(self):
        self.stale(pushed_at="2020-01-01T00:00:00Z")
        story.scan(self.cfg)
        st = story.next_step(self.cfg, "s001")
        self.assertIn("session running", st.detail)
        self.assertEqual(len(self.calls()), 1)


class CloudRelaunchTest(CloudRetrievalCase):
    def test_refused_in_a_role_session(self):
        os.environ["DELIVERY_ROLE"] = "technical-lead"
        try:
            with self.assertRaises(DeliveryError) as ctx:
                story.relaunch(self.cfg, "s001")
            err = io.StringIO()
            with redirect_stderr(err), redirect_stdout(io.StringIO()):
                self.assertNotEqual(cli_main(["story", "next", "s001", "--relaunch"]), 0)
        finally:
            os.environ.pop("DELIVERY_ROLE")
        self.assertIn("human gesture", ctx.exception.message)
        self.assertEqual(len(self.calls()), 1)
        self.assertNotIn("ended", self.entry())

    def test_abandons_the_live_session_and_starts_another_from_the_local_head(self):
        self.push_commit({"a.txt": "1\n"})
        self.pull()
        local = self.head()
        old = self.entry()
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            self.assertEqual(cli_main(["story", "next", "s001", "--relaunch"]), 0)
        self.assertEqual(len(self.calls()), 2)
        info = self.entry()
        self.assertNotIn("ended", info)
        self.assertEqual(info["head"], local)
        self.assertGreaterEqual(info["pushed_at"], old["pushed_at"])
        (event,) = self.events("resume")
        self.assertEqual(event["evidence"], SESSION)
        self.assertIn("abandoned", event["text"])
        self.assertIn("resume", self.calls()[1]["argv"][1])

    def test_a_session_ended_by_its_outcome_cannot_be_relaunched(self):
        self.push_commit({"docs/stories/s001/report.md": self.REPORT})
        self.pull()
        with self.assertRaises(DeliveryError) as ctx:
            story.relaunch(self.cfg, "s001")
        self.assertEqual(ctx.exception.code, EXIT_PRECONDITION)
        self.assertEqual(len(self.calls()), 1)

    def test_a_local_implementer_cannot_be_relaunched(self):
        info = self.entry()
        info["window"] = "fake"
        story._save_entry(self.cfg, "s001", info)
        with self.assertRaises(DeliveryError):
            story.relaunch(self.cfg, "s001")

    def test_init_asks_before_a_relaunch(self):
        from deliveryctl import init
        for launcher in ("deliveryctl", ".delivery/deliveryctl"):
            self.assertIn(f"Bash({launcher} story next *--relaunch*)", init.ask_rules())
