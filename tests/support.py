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


# A fake 'gh' that plays GitHub against the local bare 'origin': a merge request per branch,
# its CI read from FAKE_FORGE_DIR/checks (green by default; 'down' in that file makes the forge
# unreachable), and a merge that really merges the branch into the target branch of origin.
FAKE_FORGE = r'''#!PYTHON
import json, os, subprocess, sys, tempfile
from pathlib import Path
home = Path(os.environ["FAKE_FORGE_DIR"])
store = home / "requests.json"
requests = json.loads(store.read_text()) if store.exists() else {}
with (home / "calls").open("a") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\n")
checks = (home / "checks").read_text().strip() if (home / "checks").exists() else "green"
args = sys.argv[1:]
def opt(name):
    return args[args.index(name) + 1] if name in args else ""
def git(*argv, cwd=None):
    return subprocess.run(["git", *argv], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
if checks == "down":
    sys.exit("HTTP 503: service unavailable")
if args[:2] == ["repo", "view"]:
    print(json.dumps({"visibility": (home / "visibility").read_text().strip() if (home / "visibility").exists() else "PRIVATE"}))
elif args[:2] == ["pr", "view"]:
    req = requests.get(args[2])
    if not req:
        sys.exit('no pull requests found for branch "%s"' % args[2])
    rollup = {"green": [{"conclusion": "SUCCESS"}], "red": [{"conclusion": "FAILURE"}],
              "pending": [{"status": "IN_PROGRESS"}], "none": []}[checks]
    print(json.dumps({"url": req["url"], "state": req["state"], "statusCheckRollup": rollup,
                      "mergeStateStatus": "CLEAN"}))
elif args[:2] == ["pr", "create"]:
    head = opt("--head")
    url = "https://forge.test/pr/%d" % (len(requests) + 1)
    requests[head] = {"url": url, "state": "OPEN", "base": opt("--base"), "title": opt("--title")}
    store.write_text(json.dumps(requests))
    print(url)
elif args[:2] == ["pr", "merge"]:
    branch = args[2]
    req = requests[branch]
    origin = git("remote", "get-url", "origin")
    with tempfile.TemporaryDirectory() as tmp:
        git("clone", "--quiet", "--branch", req["base"], origin, tmp)
        git("fetch", "--quiet", "origin", branch, cwd=tmp)
        head = opt("--match-head-commit")
        if head and git("rev-parse", "FETCH_HEAD", cwd=tmp) != head:
            sys.exit("head commit does not match")
        git("merge", "--quiet", "--no-ff", "FETCH_HEAD", "-m", opt("--subject"), "-m", opt("--body"), cwd=tmp)
        git("push", "--quiet", "origin", req["base"], cwd=tmp)
    req["state"] = "MERGED"
    store.write_text(json.dumps(requests))
else:
    sys.exit(2)
'''


def fake_forge(tmp: Path) -> Path:
    """Put the fake 'gh' first on PATH; returns its folder (calls, checks, requests.json)."""
    home = tmp / "forge"
    tool = write(home / "bin" / "gh", FAKE_FORGE.replace("PYTHON", sys.executable, 1))
    tool.chmod(0o755)
    os.environ["FAKE_FORGE_DIR"] = str(home)
    os.environ["PATH"] = f"{home / 'bin'}{os.pathsep}{os.environ['PATH']}"
    return home


class RepoCase(unittest.TestCase):
    """Each test gets a bare 'origin', a main checkout with one commit on 'main', and an
    isolated HOME / XDG dirs so no user setting leaks in or out. The checkout carries a stub
    agent per role in .claude/agents/, as an equipped project does (`with_agents = False` for
    the tests of init, which writes them)."""

    with_agents = True

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dm-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env_backup = dict(os.environ)
        for key in [k for k in os.environ if k.startswith("DELIVERY_") or k in ("CLAUDECODE", "CLAUDE_CODE_REMOTE")]:
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
        from deliveryctl.core import ROLES
        for role in ROLES if self.with_agents else ():     # the project copy role sessions launch from
            write(self.repo / ".claude" / "agents" / f"{role}.md", f"---\nname: {role}\n---\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "--quiet", "-m", "initial")
        git(self.repo, "remote", "add", "origin", str(self.origin))
        git(self.repo, "push", "--quiet", "-u", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        self.forge_dir = fake_forge(self.tmp)  # never the real forge, whatever a test sets
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
