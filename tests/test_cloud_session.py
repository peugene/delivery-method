"""The engine inside a cloud session (CLAUDE_CODE_REMOTE=true): the gestures that start sessions,
push, tag or merge are refused, the checking verbs work, no herdr is probed, doctor skips the
owner's computer; the setup script of the cloud environment."""

import io
import os
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from support import ROOT, RepoCase, git, write

from deliveryctl import cli, config, window

REFUSED = [
    ["run"], ["merge", "s001"], ["submit", "s001"], ["story", "open", "s001"], ["story", "next", "s001"],
    ["story", "wait", "s001"], ["qualify", "run", "i1"], ["qualify", "submit", "i1"], ["nightly"],
    ["spec", "release", "1.0.0"], ["init", "--role", "impl", "--forge", "github"], ["note", "hello"],
    ["journal", "report"],
]


class CloudSessionTest(RepoCase):
    with_agents = False

    def setUp(self):
        super().setUp()
        os.environ["CLAUDE_CODE_REMOTE"] = "true"

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def equip(self):
        os.environ.pop("CLAUDE_CODE_REMOTE")
        code, out = self.cli("init", "--role", "impl", "--forge", "github")
        self.assertEqual(code, 0, out)
        os.environ["CLAUDE_CODE_REMOTE"] = "true"

    def test_refused_gestures_exit_4_and_do_nothing(self):
        before = git(self.repo, "status", "--porcelain")
        for argv in REFUSED:
            with self.subTest(argv=argv):
                code, out = self.cli(*argv)
                self.assertEqual(code, 4, out)
                self.assertIn("session cloud", out)
                self.assertIn("depuis votre ordinateur", out)
        self.assertEqual(git(self.repo, "status", "--porcelain"), before)
        self.assertFalse((self.repo / ".delivery").exists())
        self.assertEqual(git(self.repo, "worktree", "list").count("\n"), 0)

    def test_checking_verbs_work(self):
        self.equip()
        write(self.repo / "spec" / "README.md", "# spec\n")
        for argv in (["cards", "lint"], ["cards", "list"], ["cards", "order"], ["story", "status"],
                     ["doctor"], ["journal", "setup"]):
            with self.subTest(argv=argv):
                code, out = self.cli(*argv)
                self.assertEqual(code, 0, out)
                self.assertNotIn("session cloud", out)

    def test_window_is_terminal_without_probing_herdr(self):
        os.environ.pop("DELIVERY_WINDOW", None)
        write(self.home / ".config" / "delivery-method" / "machine.toml", 'window = "herdr"\n')
        with mock.patch("deliveryctl.window.herdr.HerdrWindow.probe", return_value=True) as probe:
            self.assertEqual(window.get(self.repo).name, "terminal")
            probe.assert_not_called()
            del os.environ["CLAUDE_CODE_REMOTE"]
            self.assertEqual(window.get(self.repo).name, "herdr")

    def test_doctor_says_it_is_a_cloud_session_and_skips_the_computer_checks(self):
        self.equip()
        write(self.home / ".config" / "delivery-method" / "machine.toml", 'notify_cmd = "/nonexistent/notify"\n')
        code, out = self.cli("doctor")
        self.assertEqual(code, 0)
        self.assertIn("note: cloud session:", out)
        for skipped in ("ok: machine settings", "notify_cmd", "plugin not found", "claude CLI"):
            self.assertNotIn(skipped, out)
        del os.environ["CLAUDE_CODE_REMOTE"]
        self.assertIn("ok: machine settings", self.cli("doctor")[1])


class CloudSetupScriptTest(RepoCase):
    SCRIPT = ROOT / "templates" / "project" / "cloud-setup.sh"

    def test_valid_shell(self):
        subprocess.run(["bash", "-n", str(self.SCRIPT)], check=True)

    def test_exits_0_when_there_is_nothing_to_install(self):
        bin_dir = self.tmp / "bin"
        write(bin_dir / "just", "#!/bin/sh\n")
        (bin_dir / "just").chmod(0o755)
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
        proc = subprocess.run(["bash", str(self.SCRIPT)], cwd=self.repo, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_exits_0_when_installs_fail(self):
        write(self.repo / "spec" / "acceptance" / "package.json", '{"devDependencies": {"@playwright/test": "1"}}')
        bin_dir = self.tmp / "bin"
        for name in ("npm", "npx", "python3", "pip"):
            write(bin_dir / name, "#!/bin/sh\nexit 1\n")
            (bin_dir / name).chmod(0o755)
        env = dict(os.environ, PATH=f"{bin_dir}:/usr/bin:/bin")
        proc = subprocess.run(["bash", str(self.SCRIPT)], cwd=self.repo, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
