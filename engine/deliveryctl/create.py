"""Creating the repository on the forge for `deliveryctl init` (CONTRACTS.md §12.2): who the owner
is, which git address a public GitHub repository gets, and the `gh` or `glab` gesture itself."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .core import EXIT_ERROR, EXIT_TOOL, fail, run

NOREPLY = "@users.noreply.github.com"
TOOLS = {"github": "gh", "gitlab": "glab"}
NAME_RX = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")


@dataclass
class Target:
    """A repository to create: on GitHub under the `gh` user, on GitLab in a group (or the user's
    namespace) of a host ('' = the default host of `glab`)."""
    forge: str
    owner: str
    name: str
    visibility: str
    host: str = ""
    login: str = ""                  # GitHub only: the user and the id of their noreply address
    uid: str = ""
    protocol: str = "https"

    @property
    def path(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def where(self) -> str:
        return "GitHub" if self.forge == "github" else f"GitLab{' ' + self.host if self.host else ''}"

    def origin_url(self) -> str:
        """The address `origin` will have, in the style of the tool's configuration."""
        host = "github.com" if self.forge == "github" else self.host or "gitlab.com"
        return f"git@{host}:{self.path}.git" if self.protocol == "ssh" else f"https://{host}/{self.path}.git"


def noreply(login: str, uid: str) -> str:
    return f"{uid}+{login}{NOREPLY}"


def _env(host: str) -> dict | None:
    return {"GITLAB_HOST": host} if host else None


def _tool(forge: str) -> str:
    tool = TOOLS[forge]
    if not shutil.which(tool):
        fail(EXIT_TOOL, f"forge = {forge} needs the '{tool}' command")
    return tool


def _user(forge: str, host: str = "") -> dict:
    tool = _tool(forge)
    proc = run([tool, "api", "user"], check=False, timeout=60, env=_env(host))
    try:
        data = json.loads(proc.stdout) if proc.returncode == 0 else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or not (data.get("login") or data.get("username")):
        said = " ".join((proc.stderr or proc.stdout or "").split())[:200]
        fail(EXIT_TOOL, f"'{tool} api user' did not answer ({said or f'exit {proc.returncode}'}): "
                        f"log in with '{tool} auth login'")
    return data


def github_user() -> tuple[str, str]:
    """(login, numeric id) of the `gh` user."""
    data = _user("github")
    return str(data["login"]), str(data.get("id") or "")


def git_protocol(forge: str, host: str = "") -> str:
    proc = run([TOOLS[forge], "config", "get", "git_protocol"], check=False, timeout=15, env=_env(host))
    said = proc.stdout.strip() if proc.returncode == 0 else ""
    return said if said in ("ssh", "https") else "https"


def resolve(forge: str, name: str, visibility: str, machine: dict) -> Target:
    """Where a repository called `name` would be created, with what the forge knows of the owner."""
    if not NAME_RX.match(name):
        fail(EXIT_ERROR, f"cannot name a repository '{name}' (letters, digits, '.', '-' and '_'): "
                         "give a name, deliveryctl init <layout> <name>")
    if forge == "github":
        if visibility == "internal":
            fail(EXIT_ERROR, "visibility internal exists on GitLab only: use --private or --public on GitHub")
        login, uid = github_user()
        target = Target("github", login, name, visibility, login=login, uid=uid)
    else:
        host = re.sub(r"^[a-z]+://|/+$", "", machine.get("gitlab_host", "").strip())
        owner = machine.get("gitlab_group", "").strip("/ ") or str(_user("gitlab", host).get("username") or "")
        if not owner:
            fail(EXIT_TOOL, "cannot tell the GitLab namespace: set gitlab_group in machine.toml")
        target = Target("gitlab", owner, name, visibility, host=host)
    target.protocol = git_protocol(forge, target.host)
    return target


def create(root: Path, target: Target) -> None:
    """Create the repository on the forge and make it the `origin` of the repository in `root`."""
    tool = _tool(target.forge)
    if target.forge == "github":
        run([tool, "repo", "create", target.path, "--public" if target.visibility == "public" else "--private",
             "--source", ".", "--remote", "origin"], cwd=root, timeout=120)
        return
    env = _env(target.host)
    run([tool, "repo", "create", target.path, f"--{target.visibility}"], cwd=root, env=env, timeout=120)
    proc = run([tool, "api", f"projects/{quote(target.path, safe='')}"], cwd=root, env=env, timeout=60)
    try:
        url = json.loads(proc.stdout).get("ssh_url_to_repo" if target.protocol == "ssh" else "http_url_to_repo")
    except (json.JSONDecodeError, AttributeError):
        url = None
    if not url:
        fail(EXIT_TOOL, f"glab did not report the address of {target.path}")
    has_origin = run(["git", "remote", "get-url", "origin"], cwd=root, check=False).returncode == 0
    run(["git", "remote", "set-url" if has_origin else "add", "origin", url], cwd=root)
