"""Merge requests on the forge: GitHub through `gh`, GitLab through `glab` (CONTRACTS.md §9, §12)."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from .cards import label
from .config import Config
from .core import EXIT_PRECONDITION, EXIT_RED, EXIT_TOOL, fail, run
from .gitops import Git, story_branch


# what `gh pr view` and `glab mr view` say when the branch has no merge request
NO_REQUEST = ("no pull requests found", "no open merge request", "no merge request")


class Forge:
    def __init__(self, cfg: Config, git: Git):
        self.cfg, self.git = cfg, git
        self.kind = cfg.forge

    def _tool(self) -> str:
        tool = {"github": "gh", "gitlab": "glab"}[self.kind]
        if not shutil.which(tool):
            fail(EXIT_TOOL, f"forge = {self.kind} needs the '{tool}' command")
        return tool

    # -- merge request ----------------------------------------------------------------------
    def find(self, card_id: str) -> dict | None:
        """The open or merged merge request of a story: {url, state, checks}; None if none.
        Raises DeliveryError (EXIT_TOOL) when the forge does not answer."""
        return self._find_branch(story_branch(card_id))

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

    def _find_branch(self, branch: str) -> dict | None:
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

    def open_branch(self, branch: str, title: str, body: str) -> str:
        """Push a branch and open its merge request, or return the one already open (pushed
        again). A branch whose merge request is merged is neither pushed nor proposed again."""
        target = self.git.target_branch()
        existing = self._find_branch(branch)
        if existing and existing["state"] == "merged":
            fail(EXIT_PRECONDITION, f"the merge request of {branch} is already merged: {existing['url']}")
        self.git.push(branch)
        if existing and existing["state"] in ("open", "opened"):
            return existing["url"]
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(body)
            body_file = fh.name
        try:
            if self.kind == "github":
                proc = run([self._tool(), "pr", "create", "--base", target, "--head", branch,
                            "--title", title, "--body-file", body_file], cwd=self.git.cwd)
            else:
                proc = run([self._tool(), "mr", "create", "--source-branch", branch,
                            "--target-branch", target, "--title", title,
                            "--description", Path(body_file).read_text(encoding="utf-8"), "--yes"],
                           cwd=self.git.cwd)
        finally:
            Path(body_file).unlink(missing_ok=True)
        return proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""

    def merge(self, card_id: str, subject: str, trailers: list[tuple[str, str]], head: str = "") -> str:
        """Merge a story whose merge request is green, by a merge commit of the checked head;
        returns a one-line summary."""
        body = "\n".join(f"{k}: {v}" for k, v in trailers)
        mr = self.find(card_id)
        if not mr or mr["state"] not in ("open", "opened"):
            fail(EXIT_PRECONDITION, f"no open merge request for {story_branch(card_id)}")
        if mr["checks"] != "green":
            fail(EXIT_RED if mr["checks"] == "red" else EXIT_PRECONDITION,
                 f"the CI of the merge request is {mr['checks']}, not green"
                 + ("" if mr["checks"] == "red" else " (not yet: try again later)") + f": {mr['url']}")
        branch = story_branch(card_id)
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
        return f"merged {mr['url']}"


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
