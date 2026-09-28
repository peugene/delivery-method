"""Test helpers: throwaway git repositories and an isolated environment for the engine."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))


def sh(cmd, cwd, check=True, env=None, input_text=None):
    full = dict(os.environ)
    if env:
        full.update(env)
    proc = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), text=True,
                          capture_output=True, env=full, input=input_text)
    if check and proc.returncode != 0:
        raise AssertionError(f"command failed ({proc.returncode}): {cmd}\n{proc.stdout}\n{proc.stderr}")
    return proc


def git(cwd, *args, check=True):
    return sh(["git", *args], cwd, check=check).stdout.strip()


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class RepoCase(unittest.TestCase):
    """Each test gets a bare 'origin', a main checkout with one commit on 'main', and an
    isolated HOME / XDG dirs so no user setting leaks in or out."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dm-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env_backup = dict(os.environ)
        for key in [k for k in os.environ if k.startswith("DELIVERY_") or k == "CLAUDECODE"]:
            os.environ.pop(key, None)
        os.environ.update({
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "GIT_AUTHOR_NAME": "Test Owner", "GIT_AUTHOR_EMAIL": "owner@example.test",
            "GIT_COMMITTER_NAME": "Test Owner", "GIT_COMMITTER_EMAIL": "owner@example.test",
            "GIT_CONFIG_GLOBAL": str(self.home / ".gitconfig"),
            "DELIVERY_WINDOW": "terminal",
            "DELIVERY_PLUGIN_ROOT": str(ROOT),
        })
        (self.home / ".gitconfig").write_text("[init]\n\tdefaultBranch = main\n")
        self.origin = self.tmp / "origin.git"
        sh(["git", "init", "--quiet", "--bare", str(self.origin)], self.tmp)
        self.repo = self.tmp / "todo"
        self.repo.mkdir()
        git(self.repo, "init", "--quiet")
        write(self.repo / "README.md", "# todo\n")
        write(self.repo / "src" / "app.txt", "v1\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "--quiet", "-m", "initial")
        git(self.repo, "remote", "add", "origin", str(self.origin))
        git(self.repo, "push", "--quiet", "-u", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        self.cwd_backup = os.getcwd()
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.cwd_backup)
        os.environ.clear()
        os.environ.update(self.env_backup)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def commit_all(self, message="change", cwd=None):
        cwd = cwd or self.repo
        git(cwd, "add", "-A")
        git(cwd, "commit", "--quiet", "-m", message)
        return git(cwd, "rev-parse", "HEAD")
