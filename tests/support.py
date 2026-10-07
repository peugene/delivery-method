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
# unreachable; a file 'checks-<branch, / as _>' answers for that branch alone), and a merge that really merges the branch into the target branch of origin.
# It also creates repositories (a bare one under FAKE_FORGE_DIR/remotes, visibility in the file
# 'visibility'), answers 'api user' (login in the file 'login'), keeps the branch protection in
# 'protection.json' and the merge settings in 'repo_settings.json'; a file 'protection_403' makes
# the protection refuse.
FAKE_FORGE = r'''#!PYTHON
import json, os, subprocess, sys, tempfile
from pathlib import Path
home = Path(os.environ["FAKE_FORGE_DIR"])
store = home / "requests.json"
requests = json.loads(store.read_text()) if store.exists() else {}
with (home / "calls").open("a") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\n")
args = sys.argv[1:]
checks = (home / "checks").read_text().strip() if (home / "checks").exists() else "green"
if args[:2] == ["pr", "view"] and (home / ("checks-" + args[2].replace("/", "_"))).exists():
    checks = (home / ("checks-" + args[2].replace("/", "_"))).read_text().strip()
def opt(name):
    return args[args.index(name) + 1] if name in args else ""
def git(*argv, cwd=None):
    return subprocess.run(["git", *argv], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
if checks == "down":
    sys.exit("HTTP 503: service unavailable")
def seen(name, default):
    return (home / name).read_text().strip() if (home / name).exists() else default
if args[:2] == ["repo", "view"]:
    print(json.dumps({"visibility": seen("visibility", "PRIVATE"),
                      "nameWithOwner": seen("repo", "test-owner/" + Path.cwd().name)}))
elif args[:2] == ["repo", "create"]:
    path = args[2]
    bare = home / "remotes" / (path + ".git")
    bare.parent.mkdir(parents=True, exist_ok=True)
    git("init", "--quiet", "--bare", str(bare))
    git("remote", "add", opt("--remote"), "https://github.com/%s.git" % path)
    (home / "visibility").write_text("PUBLIC" if "--public" in args else "PRIVATE")
    (home / "created").write_text(path)
elif args[:2] == ["config", "get"]:
    print(seen("git_protocol", "https"))
elif args[:1] == ["api"]:
    method = opt("-X") or "GET"
    path = args[1] if method == "GET" else args[args.index("-X") + 2]
    body = json.loads(sys.stdin.read()) if "--input" in args else None
    if path == "user":
        print(json.dumps({"login": seen("login", "test-owner"), "id": 4242}))
    elif path.endswith("/protection"):
        stored = home / "protection.json"
        if method == "PUT":
            if (home / "protection_403").exists():
                sys.exit("HTTP 403: Upgrade to GitHub Pro or make this repository public to enable this feature.")
            stored.write_text(json.dumps(body))
        elif not stored.exists():
            sys.exit("HTTP 404: Branch not protected")
        else:
            put = json.loads(stored.read_text())
            out = {"enforce_admins": {"enabled": put["enforce_admins"]},
                   "allow_force_pushes": {"enabled": put["allow_force_pushes"]},
                   "allow_deletions": {"enabled": put["allow_deletions"]}}
            if put["required_status_checks"]:
                contexts = put["required_status_checks"]["contexts"]
                out["required_status_checks"] = {**put["required_status_checks"],
                                                 "checks": [{"context": c} for c in contexts]}
            if put["required_pull_request_reviews"]:
                out["required_pull_request_reviews"] = put["required_pull_request_reviews"]
            if put["restrictions"]:
                out["restrictions"] = {k: [{"login" if k == "users" else "slug": v} for v in put["restrictions"][k]]
                                       for k in ("users", "teams", "apps")}
            print(json.dumps(out))
    elif method == "PATCH" and "/pulls/" in path:
        if (home / "edit_refused").exists():
            sys.exit("HTTP 422: Validation Failed")
        number = path.rsplit("/", 1)[-1]
        fields = dict(a.split("=", 1) for a in args if "=" in a and not a.startswith("-"))
        for req in requests.values():
            if req["url"].endswith("/pr/" + number):
                req.update(title=fields["title"], body=Path(fields["body"][1:]).read_text())
        store.write_text(json.dumps(requests))
    elif method == "PATCH" and path.startswith("repos/"):
        (home / "repo_settings.json").write_text(json.dumps(body))
    else:
        sys.exit(2)
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
    requests[head] = {"url": url, "state": "OPEN", "base": opt("--base"), "title": opt("--title"),
                      "body": Path(opt("--body-file")).read_text()}
    store.write_text(json.dumps(requests))
    print(url)
elif args[:2] == ["pr", "edit"]:
    sys.exit("GraphQL: Projects (classic) is being deprecated (repository.pullRequests.nodes.0.projectCards)")
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


# A fake 'glab' in the same spirit, for the tests that play GitLab: projects created as bare
# repositories under FAKE_FORGE_DIR/remotes (reachable through 'git@gitlab.test:' once the test
# maps it, see map_remotes), project settings in 'project.json', protected branches in
# 'protected.json', every call in 'glab_calls' with the GITLAB_HOST it got. 'protect_403' makes
# the writes of protection and settings refuse.
FAKE_GLAB = r'''#!PYTHON
import json, os, subprocess, sys
from pathlib import Path
from urllib.parse import unquote
home = Path(os.environ["FAKE_FORGE_DIR"])
args = sys.argv[1:]
with (home / "glab_calls").open("a") as fh:
    fh.write("[%s] %s\n" % (os.environ.get("GITLAB_HOST", ""), " ".join(args)))
fields = {args[i + 1].partition("=")[0]: args[i + 1].partition("=")[2] for i, a in enumerate(args) if a in ("-f", "-F")}
method = args[args.index("-X") + 1] if "-X" in args else ("POST" if fields else "GET")
rest = [a for i, a in enumerate(args) if i and a not in ("-X", "-f", "-F") and args[i - 1] not in ("-X", "-f", "-F")]
path = rest[0] if args[0] == "api" and rest else ""
def load(name, default):
    return json.loads((home / name).read_text()) if (home / name).exists() else default
def save(name, data):
    (home / name).write_text(json.dumps(data))
def seen(name, default):
    return (home / name).read_text().strip() if (home / name).exists() else default
refused = (home / "protect_403").exists()
if args[:2] == ["config", "get"]:
    print(seen("git_protocol", "ssh"))
elif path == "user":
    print(json.dumps({"username": seen("login", "glab-user")}))
elif args[:2] == ["repo", "create"]:
    path = args[2]
    bare = home / "remotes" / (path + ".git")
    bare.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", "--bare", str(bare)], check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://gitlab.test/%s.git" % path], check=True)
    visibility = [a[2:] for a in args if a in ("--private", "--public", "--internal")][0]
    save("created.json", {"path": path, "visibility": visibility, "host": os.environ.get("GITLAB_HOST", "")})
elif "/protected_branches" in path:
    protected = load("protected.json", {})
    where = unquote(path).split("/protected_branches")
    name = where[1].strip("/") or fields.get("name", "")
    if method == "GET":
        if name not in protected:
            sys.exit("404 Not Found")
        print(json.dumps(protected[name]))
    elif refused:
        sys.exit("403 Forbidden")
    elif method == "DELETE":
        protected.pop(name, None)
        save("protected.json", protected)
    else:
        protected[name] = {"name": name, "allow_force_push": fields["allow_force_push"] == "true",
                           "push_access_levels": [{"access_level": int(fields["push_access_level"])}],
                           "merge_access_levels": [{"access_level": int(fields["merge_access_level"])}]}
        save("protected.json", protected)
elif path.startswith("projects/"):
    path = unquote(path[len("projects/"):])
    project = load("project.json", {"only_allow_merge_if_pipeline_succeeds": False, "merge_method": "merge_commit"})
    if method == "PUT":
        if refused:
            sys.exit("403 Forbidden")
        for key, value in fields.items():
            project[key] = value == "true" if value in ("true", "false") else value
        save("project.json", project)
    else:
        print(json.dumps({**project, "visibility": load("created.json", {}).get("visibility", "private"),
                          "ssh_url_to_repo": "git@gitlab.test:%s.git" % path,
                          "http_url_to_repo": "https://gitlab.test/%s.git" % path}))
else:
    sys.exit(2)
'''


def fake_glab(home: Path) -> None:
    """Put the fake 'glab' first on PATH, next to the fake 'gh' of `fake_forge`."""
    tool = write(home / "bin" / "glab", FAKE_GLAB.replace("PYTHON", sys.executable, 1))
    tool.chmod(0o755)


def map_remotes(home: Path, *prefixes: str) -> None:
    """Make git read the fake forges' addresses (https://github.com/…, git@gitlab.test:…) as the
    bare repositories their fake tools create."""
    for prefix in prefixes:
        sh(["git", "config", "--global", "--add", f"url.{home / 'remotes'}/.insteadOf", prefix], home)


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
