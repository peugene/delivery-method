"""The story-implementer as a Claude Code cloud session: the setting, the launch through a
pseudo-terminal after the push of the story branch, the cloud window and the registry it shares
with the other windows, `story status` and `doctor`. A fake `claude` stands for the real one."""

import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from support import RepoCase, git, sh, write
from test_story import CARD, ORDER

from deliveryctl import config, doctor, roles, story
from deliveryctl.cli import main as cli_main
from deliveryctl.core import EXIT_ERROR, EXIT_TOOL, DeliveryError
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
        return config.parse(__import__("tomllib").loads(text), self.repo)

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

    def test_stop_does_nothing_and_a_cloud_session_is_not_a_stall(self):
        self.configure(levers="stall_minutes = 0\n")
        self.open()
        self.assertEqual(story.check_stall(self.cfg, "s001"), [])
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
