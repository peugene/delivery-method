"""Merge requests on the forge: GitHub through `gh`, GitLab through `glab` (CONTRACTS.md §9, §12)."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote, urlparse

from .cards import label
from .config import Config
from .core import EXIT_PRECONDITION, EXIT_RED, EXIT_TOOL, DeliveryError, fail, run
from .gitops import Git, story_branch


# what `gh pr view` and `glab mr view` say when the branch has no merge request
NO_REQUEST = ("no pull requests found", "no open merge request", "no merge request")
# the CI job a merge waits for once the product's checks can pass (templates/project/github-ci.yml)
CHECK_JOB = "checks"
MERGE_ACCESS = 40                   # GitLab access levels: maintainers merge, no one pushes
NO_ACCESS = 0
PROTECTION_FLAGS = ("required_linear_history", "required_conversation_resolution", "block_creations",
                    "lock_branch", "allow_fork_syncing")
REVIEW_KEYS = ("required_approving_review_count", "dismiss_stale_reviews", "require_code_owner_reviews",
               "require_last_push_approval")


def parse_remote(url: str) -> tuple[str, str]:
    """(host, 'group/name') of a git address; ('', '') for a local path."""
    url = url.strip()
    if "://" in url:
        parsed = urlparse(url)
        host, path = parsed.hostname or "", parsed.path
    else:
        found = re.match(r"^[\w.-]+@([\w.-]+):(?!//)(.+)$", url)
        host, path = (found.group(1), found.group(2)) if found else ("", "")
    if not host:
        return "", ""
    return host, re.sub(r"(\.git)?/*$", "", path.strip("/"))


class Forge:
    def __init__(self, cfg: Config | None, git: Git, kind: str = ""):
        self.cfg, self.git = cfg, git
        self.kind = kind or cfg.forge

    def _tool(self) -> str:
        tool = {"github": "gh", "gitlab": "glab"}[self.kind]
        if not shutil.which(tool):
            fail(EXIT_TOOL, f"forge = {self.kind} needs the '{tool}' command")
        return tool

    def _origin(self) -> tuple[str, str]:
        # as written in the configuration: `get-url` would show an address after its rewrite rules
        return parse_remote(self.git.out("config", "--get", "remote.origin.url", check=False))

    def _call(self, argv: list[str], body: dict | None = None):
        """One `gh` or `glab` call on this repository's host; never raises on a refusal."""
        host = self._origin()[0] if self.kind == "gitlab" else ""
        return run([self._tool(), *argv], cwd=self.git.cwd, check=False, timeout=60,
                   env={"GITLAB_HOST": host} if host else None,
                   input_text=json.dumps(body) if body is not None else None)

    # -- repository and protection of its default branch ------------------------------------
    def repo(self) -> dict:
        """{path, visibility} of the repository origin points to: 'owner/name' and 'private',
        'public' or 'internal'; what the forge does not say is left empty."""
        path, visibility = self._origin()[1], ""
        try:
            if self.kind == "github":
                proc = self._call(["repo", "view", "--json", "nameWithOwner,visibility"])
            else:
                proc = self._call(["api", f"projects/{quote(path, safe='')}"]) if path else None
            data = json.loads(proc.stdout) if proc is not None and proc.returncode == 0 else {}
        except (DeliveryError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            path = data.get("nameWithOwner") or path
            visibility = str(data.get("visibility") or "").lower()
        return {"path": path, "visibility": visibility}

    def protect(self, branch: str, checks: bool) -> list[str]:
        """Protect the default branch: a merge request, no force push, no deletion, merge commits
        only, and the CI required when `checks`. Returns a note for each setting the forge refuses."""
        path = self.repo()["path"]
        if not path:
            return [f"protection of {branch} skipped: the repository path cannot be read from origin"]
        notes = []
        if self.kind == "github":
            body = {"required_status_checks": {"strict": True, "contexts": [CHECK_JOB]} if checks else None,
                    "enforce_admins": True, "required_pull_request_reviews": {"required_approving_review_count": 0},
                    "restrictions": None, "allow_force_pushes": False, "allow_deletions": False}
            proc = self._call(["api", "-X", "PUT", f"repos/{path}/branches/{branch}/protection", "--input", "-"], body)
            if proc.returncode != 0:
                notes.append(f"{_refusal('branch protection of ' + branch, proc)}: set it in the repository settings "
                             "(pull request required, no force push, no deletion)")
            proc = self._call(["api", "-X", "PATCH", f"repos/{path}", "--input", "-"],
                              {"allow_merge_commit": True, "allow_squash_merge": False, "allow_rebase_merge": False})
            if proc.returncode != 0:
                notes.append(f"{_refusal('merge methods', proc)}: allow merge commits only in the repository settings")
            return notes
        project = f"projects/{quote(path, safe='')}"
        shown = f"{project}/protected_branches/{quote(branch, safe='')}"
        proc = self._call(["api", shown])
        current = _json(proc.stdout) if proc.returncode == 0 else None
        if current is not None and not _gitlab_protected(current):
            self._call(["api", "-X", "DELETE", shown])        # GitLab protects the default branch itself, with other levels
            current = None
        if current is None:
            proc = self._call(["api", "-X", "POST", f"{project}/protected_branches", "-f", f"name={branch}",
                               "-F", f"push_access_level={NO_ACCESS}", "-F", f"merge_access_level={MERGE_ACCESS}",
                               "-F", "allow_force_push=false"])
            if proc.returncode != 0:
                notes.append(f"{_refusal('protected branch ' + branch, proc)}: protect it in the project settings "
                             "(push no one, merge maintainers, no force push)")
        proc = self._call(["api", "-X", "PUT", project, "-f", "merge_method=merge", "-F",
                           f"only_allow_merge_if_pipeline_succeeds={str(checks).lower()}"])
        if proc.returncode != 0:
            notes.append(f"{_refusal('project merge settings', proc)}: use the merge commit method in the project settings")
        return notes

    def require_checks(self) -> str:
        """Make a merge wait for the CI, once the product's checks can pass: a no-op when the
        protection already requires it or does not exist. Returns the line to print, or ''.
        A forge that refuses is not an error here: the merge has happened."""
        try:
            path = self.repo()["path"]
            if not path or self.kind not in ("github", "gitlab"):
                return ""
            branch = self.git.target_branch()
            done = (self._checks_github if self.kind == "github" else self._checks_gitlab)(path, branch)
        except DeliveryError:
            return ""
        return f"protection: the CI is now required on {branch} before a merge" if done else ""

    def _checks_github(self, path: str, branch: str) -> bool:
        proc = self._call(["api", f"repos/{path}/branches/{branch}/protection"])
        current = _json(proc.stdout) if proc.returncode == 0 else None
        if not isinstance(current, dict):
            return False
        required = current.get("required_status_checks")
        contexts = list(required.get("contexts") or []) if isinstance(required, dict) else []
        if CHECK_JOB in contexts:
            return False

        def flag(key):
            value = current.get(key)
            return bool(value.get("enabled")) if isinstance(value, dict) else False
        reviews, limits = current.get("required_pull_request_reviews"), current.get("restrictions")
        # the owner's own settings are kept: only the required check is added
        body = {"required_status_checks": {"strict": True, "contexts": contexts + [CHECK_JOB]},
                "enforce_admins": flag("enforce_admins"),
                "required_pull_request_reviews": {k: reviews[k] for k in REVIEW_KEYS if k in reviews}
                if isinstance(reviews, dict) else None,
                "restrictions": {kind: [item.get("login") or item.get("slug") for item in limits.get(kind) or []]
                                 for kind in ("users", "teams", "apps")} if isinstance(limits, dict) else None,
                "allow_force_pushes": flag("allow_force_pushes"), "allow_deletions": flag("allow_deletions")}
        body.update({key: flag(key) for key in PROTECTION_FLAGS if key in current})
        proc = self._call(["api", "-X", "PUT", f"repos/{path}/branches/{branch}/protection", "--input", "-"], body)
        return proc.returncode == 0

    def _checks_gitlab(self, path: str, branch: str) -> bool:
        project = f"projects/{quote(path, safe='')}"
        proc = self._call(["api", project])
        current = _json(proc.stdout) if proc.returncode == 0 else None
        if not isinstance(current, dict) or current.get("only_allow_merge_if_pipeline_succeeds") is not False:
            return False
        proc = self._call(["api", "-X", "PUT", project, "-F", "only_allow_merge_if_pipeline_succeeds=true"])
        return proc.returncode == 0

    # -- merge request ----------------------------------------------------------------------
    def find(self, card_id: str) -> dict | None:
        """The open or merged merge request of a story: {url, state, checks}; None if none.
        Raises DeliveryError (EXIT_TOOL) when the forge does not answer."""
        return self.find_branch(story_branch(card_id))

    def _view(self, argv: list[str], branch: str) -> dict | None:
        """JSON of a merge request view; None when the forge says the branch has none."""
        proc = run(argv, cwd=self.git.cwd, check=False, timeout=60)
        if proc.returncode != 0:
            said = (proc.stderr or proc.stdout or "").strip()
            if any(text in said.lower() for text in NO_REQUEST):
                return None
            fail(EXIT_TOOL, f"forge unreachable ({' '.join(argv[:3])} {branch}): "
                            f"{' '.join(said.split())[:300] or f'exit {proc.returncode}'}")
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            fail(EXIT_TOOL, f"forge answer not understood ({' '.join(argv[:3])} {branch})")

    def find_branch(self, branch: str) -> dict | None:
        """Like `find`, for any branch."""
        if self.kind == "github":
            data = self._view([self._tool(), "pr", "view", branch, "--json",
                               "url,state,statusCheckRollup,mergeStateStatus"], branch)
            if data is None:
                return None
            return {"url": data.get("url"), "state": data.get("state", "").lower(),
                    "checks": _github_checks(data.get("statusCheckRollup") or [])}
        if self.kind == "gitlab":
            data = self._view([self._tool(), "mr", "view", branch, "-F", "json"], branch)
            if data is None:
                return None
            pipeline = ((data.get("head_pipeline") or data.get("pipeline") or {}).get("status") or "none")
            checks = {"success": "green", "failed": "red", "canceled": "red"}.get(pipeline, "pending")
            if pipeline == "none":
                checks = "none"
            return {"url": data.get("web_url"), "state": data.get("state", ""), "checks": checks}
        return None

    def open(self, card_id: str, title: str, body: str) -> str:
        """Push the story branch and open its merge request; returns its URL."""
        return self.open_branch(story_branch(card_id), title, body)

    def open_branch(self, branch: str, title: str, body: str, refresh: bool = False) -> str:
        """Push a branch and open its merge request, or return the one already open (pushed
        again; with `refresh`, its title and description are rewritten). A branch whose merge
        request is merged is neither pushed nor proposed again."""
        target = self.git.target_branch()
        existing = self.find_branch(branch)
        if existing and existing["state"] == "merged":
            fail(EXIT_PRECONDITION, f"the merge request of {branch} is already merged: {existing['url']}")
        self.git.push(branch)
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(body)
            body_file = fh.name
        try:
            if existing and existing["state"] in ("open", "opened"):
                if refresh:
                    self._rewrite(existing["url"], title, body_file, body)
                return existing["url"]
            if self.kind == "github":
                proc = run([self._tool(), "pr", "create", "--base", target, "--head", branch,
                            "--title", title, "--body-file", body_file], cwd=self.git.cwd)
            else:
                proc = run([self._tool(), "mr", "create", "--source-branch", branch,
                            "--target-branch", target, "--title", title,
                            "--description", body, "--yes"], cwd=self.git.cwd)
        finally:
            Path(body_file).unlink(missing_ok=True)
        return proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""

    def _rewrite(self, url: str, title: str, body_file: str, body: str) -> None:
        """Rewrite the title and description of an open merge request. Through the REST API on
        GitHub: `gh pr edit` reads fields some GitHub versions no longer serve, and fails there. A
        refusal is only a note: the branch is pushed, the description is not what a GO waits for."""
        if self.kind == "github":
            path = self.repo()["path"] or "{owner}/{repo}"
            proc = self._call(["api", "-X", "PATCH", f"repos/{path}/pulls/{url.rstrip('/').rsplit('/', 1)[-1]}",
                               "-f", f"title={title}", "-F", f"body=@{body_file}"])
        else:
            proc = self._call(["mr", "update", self.git.branch(), "--title", title, "--description", body])
        if proc.returncode != 0:
            print(f"note: {_refusal('the description of ' + url, proc)}; it stays as it was", flush=True)

    def merge(self, card_id: str, subject: str, trailers: list[tuple[str, str]], head: str = "") -> str:
        """Merge a story whose merge request is green, by a merge commit of the checked head;
        returns a one-line summary."""
        return self.merge_branch(story_branch(card_id), subject, trailers, head)

    def merge_branch(self, branch: str, subject: str, trailers: list[tuple[str, str]], head: str = "") -> str:
        """Merge the merge request of a branch the same way."""
        body = "\n".join(f"{k}: {v}" for k, v in trailers)
        mr = self.find_branch(branch)
        if not mr or mr["state"] not in ("open", "opened"):
            fail(EXIT_PRECONDITION, f"no open merge request for {branch}")
        if mr["checks"] != "green":
            fail(EXIT_RED if mr["checks"] == "red" else EXIT_PRECONDITION,
                 f"the CI of the merge request is {mr['checks']}, not green"
                 + ("" if mr["checks"] == "red" else " (not yet: try again later)") + f": {mr['url']}")
        if self.kind == "github":
            args = [self._tool(), "pr", "merge", branch, "--merge", "--subject", subject, "--body", body]
            if head:
                args += ["--match-head-commit", head]
        else:
            args = [self._tool(), "mr", "merge", branch, "--yes", "--message", subject + "\n\n" + body]
            if head:
                args += ["--sha", head]
        run(args, cwd=self.git.cwd)
        self.git.fetch()
        line = self.require_checks()
        return f"merged {mr['url']}" + (f"\n{line}" if line else "")


def _json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _refusal(what: str, proc) -> str:
    said = " ".join((proc.stderr or proc.stdout or "").split())[:160]
    return f"{what} refused by the forge ({said or f'exit {proc.returncode}'})"


def _gitlab_protected(data) -> bool:
    """A protected branch with the levels the method wants: push no one, merge maintainers, no force push."""
    def levels(key):
        return {item.get("access_level") for item in (data.get(key) or []) if isinstance(item, dict)}
    return isinstance(data, dict) and levels("push_access_levels") == {NO_ACCESS} \
        and levels("merge_access_levels") == {MERGE_ACCESS} and not data.get("allow_force_push")


def _github_checks(rollup: list) -> str:
    if not rollup:
        return "none"
    states = []
    for item in rollup:
        conclusion = (item.get("conclusion") or item.get("state") or "").upper()
        status = (item.get("status") or "").upper()
        if status and status != "COMPLETED" and not conclusion:
            states.append("pending")
        elif conclusion in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            states.append("green")
        elif conclusion in ("", "PENDING", "EXPECTED", "QUEUED", "IN_PROGRESS"):
            states.append("pending")
        else:
            states.append("red")
    if "red" in states:
        return "red"
    return "pending" if "pending" in states else "green"


def request_body(card_id: str, title: str, report: str | None, verification: str | None,
                 review: str | None, gate_problems: list[str]) -> str:
    parts = [f"# {label(card_id, title)}", "",
             f"Story folder: `docs/stories/{card_id}/` (order, report, verification, review).", ""]
    parts += ["## Report", "", (report or "_missing_").strip(), ""]
    parts += ["## Verification", "", "```", _tail(verification), "```", ""]
    parts += ["## Review", "", "```", _tail(review), "```", ""]
    parts += ["## Integration check", ""]
    parts += [f"- {p}" for p in gate_problems] or ["- green"]
    return "\n".join(parts) + "\n"


def _tail(text: str | None, lines: int = 6) -> str:
    if not text:
        return "missing"
    kept = [line for line in text.strip().splitlines() if line.strip()]
    return "\n".join(kept[-lines:])
