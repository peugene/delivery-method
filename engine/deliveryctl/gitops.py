"""Git plumbing used by every verb. The engine never force-pushes, never rewrites history and
always stages paths explicitly."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

from .core import EXIT_PRECONDITION, EXIT_TOOL, fail, run

STORIES_DIR = "docs/stories/"
TRAILER_LINE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9-]*[ \t]*:[ \t]*\S.*|[ \t]+\S.*)$")   # `Key: value`, or its continuation


def trailers_of(message: str) -> list[tuple[str, str]]:
    """The trailers of a commit message, in order: every consecutive paragraph at the end of the
    message made only of trailer lines. A tool that adds its own trailers after a blank line must
    not hide the ones above it. The first paragraph is the subject, never a trailer block."""
    paragraphs = [p.split("\n") for p in re.split(r"\n[ \t]*\n", message.replace("\r", "").strip("\n")) if p.strip()]
    block: list[str] = []
    for lines in reversed(paragraphs[1:]):
        if lines[0][0] in " \t" or not all(TRAILER_LINE.match(line) for line in lines):
            break
        block = lines + block
    found: list[tuple[str, str]] = []
    for line in block:
        if line[0] in " \t":
            if found:
                found[-1] = (found[-1][0], found[-1][1] + " " + line.strip())
            continue
        key, _, value = line.partition(":")
        found.append((key.strip(), value.strip()))
    return found


def trailer_values(message: str, key: str) -> list[str]:
    """The values of the trailer `key` (case-insensitive) in the message."""
    return [v for k, v in trailers_of(message) if k.lower() == key.lower()]


class Git:
    def __init__(self, cwd: Path):
        self.cwd = Path(cwd)

    def run(self, *args, check=True, env=None, timeout=None):
        return run(["git", *args], cwd=self.cwd, check=check, env=env, timeout=timeout)

    def out(self, *args, check=True) -> str:
        return self.run(*args, check=check).stdout.strip()

    def ok(self, *args) -> bool:
        return self.run(*args, check=False).returncode == 0

    # -- references -------------------------------------------------------------------------
    def rev(self, ref: str) -> str | None:
        proc = self.run("rev-parse", "--verify", "--quiet", ref + "^{commit}", check=False)
        return proc.stdout.strip() or None

    def head(self) -> str:
        return self.out("rev-parse", "HEAD")

    def branch(self) -> str:
        return self.out("rev-parse", "--abbrev-ref", "HEAD")

    def has_remote(self, name: str = "origin") -> bool:
        return name in self.out("remote").split()

    def target_branch(self) -> str:
        """Target branch from origin/HEAD, else main, else master (CONTRACTS.md §3)."""
        proc = self.run("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip().split("/", 1)[1]
        for var in ("GITHUB_BASE_REF", "CI_MERGE_REQUEST_TARGET_BRANCH_NAME"):
            if os.environ.get(var):
                return os.environ[var]
        for name in ("main", "master"):
            if self.rev(name) or self.rev(f"origin/{name}"):
                return name
        fail(EXIT_PRECONDITION, "cannot determine the target branch (set origin/HEAD)")

    def target_ref(self) -> str:
        """Remote-tracking ref of the target branch when it exists, else the local branch."""
        name = self.target_branch()
        return f"origin/{name}" if self.rev(f"origin/{name}") else name

    def merge_base(self, a: str, b: str) -> str:
        return self.out("merge-base", a, b)

    def is_ancestor(self, a: str, b: str) -> bool:
        return self.ok("merge-base", "--is-ancestor", a, b)

    # -- content ----------------------------------------------------------------------------
    def show(self, rev: str, path: str) -> str | None:
        proc = self.run("show", f"{rev}:{path}", check=False)
        return proc.stdout if proc.returncode == 0 else None

    def exists(self, rev: str, path: str) -> bool:
        return self.ok("cat-file", "-e", f"{rev}:{path}")

    def blob(self, rev: str, path: str) -> str | None:
        proc = self.run("rev-parse", "--verify", "--quiet", f"{rev}:{path}", check=False)
        return proc.stdout.strip() or None

    def code_tree(self, rev: str = "HEAD") -> str:
        """Code tree id (CONTRACTS.md §7.2): SHA-1 of the NUL-separated `ls-tree -r -z` entries
        whose path does not start with docs/stories/, joined by NUL (independent of quotePath)."""
        proc = subprocess.run(["git", "ls-tree", "-r", "-z", "--full-tree", rev], cwd=self.cwd,
                              capture_output=True)
        if proc.returncode != 0:
            from .core import fail as _fail
            _fail(EXIT_TOOL, f"git ls-tree failed: {proc.stderr.decode(errors='replace').strip()}")
        prefix = STORIES_DIR.encode()
        kept = [entry for entry in proc.stdout.split(b"\0")
                if entry and not entry.split(b"\t", 1)[-1].startswith(prefix)]
        return hashlib.sha1(b"\0".join(kept)).hexdigest()

    def commit_time(self, rev: str = "HEAD") -> int:
        out = self.out("log", "-1", "--format=%ct", rev, check=False)
        return int(out) if out.isdigit() else 0

    def last_commit_of(self, path: str, since: str, rev: str = "HEAD") -> str | None:
        out = self.out("log", "-1", "--format=%H", f"{since}..{rev}", "--", path, check=False)
        return out or None

    def diff_names(self, base: str, head: str = "HEAD") -> list[str]:
        out = self.out("diff", "--name-only", "--no-renames", f"{base}...{head}")
        return [line for line in out.splitlines() if line]

    def diff_status(self, base: str, head: str = "HEAD") -> list[tuple[str, str]]:
        out = self.out("diff", "--name-status", "--no-renames", f"{base}...{head}")
        rows = []
        for line in out.splitlines():
            status, _, path = line.partition("\t")
            rows.append((status[:1], path))
        return rows

    def first_commit_files(self, base: str, head: str = "HEAD") -> list[str]:
        commits = self.out("rev-list", "--reverse", f"{base}..{head}").split()
        if not commits:
            return []
        out = self.out("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commits[0])
        return [line for line in out.splitlines() if line]

    def dirty(self) -> list[str]:
        out = self.run("status", "--porcelain", "--untracked-files=all").stdout
        return [line[3:] for line in out.splitlines() if line]

    # -- writing ----------------------------------------------------------------------------
    def commit(self, paths: list[str], subject: str, trailers: list[tuple[str, str]] | None = None,
               body: str = "", allow_empty: bool = False) -> str:
        if paths:
            self.run("add", "--", *paths)
        message = subject.strip() + "\n"
        if body.strip():
            message += "\n" + body.strip() + "\n"
        if trailers:
            message += "\n" + "\n".join(f"{k}: {v}" for k, v in trailers) + "\n"
        args = ["commit", "--quiet", "-F", "-"]
        if allow_empty:
            args.append("--allow-empty")
        proc = run(["git", *args], cwd=self.cwd, check=False, input_text=message)
        if proc.returncode != 0:
            fail(EXIT_TOOL, f"git commit failed: {(proc.stderr or proc.stdout).strip()}")
        return self.head()

    def fetch(self, *refs: str) -> None:
        if self.has_remote():
            self.run("fetch", "--quiet", "origin", *refs, timeout=120)

    def push(self, branch: str) -> None:
        self.run("push", "--quiet", "--set-upstream", "origin", f"{branch}:{branch}", timeout=180)

    # -- worktrees --------------------------------------------------------------------------
    def worktrees(self) -> list[dict]:
        out = self.out("worktree", "list", "--porcelain")
        items, cur = [], {}
        for line in out.splitlines() + [""]:
            if not line:
                if cur:
                    items.append(cur)
                cur = {}
                continue
            key, _, value = line.partition(" ")
            cur[key] = value or True
        return items

    def worktree_for(self, branch: str) -> Path | None:
        for item in self.worktrees():
            if item.get("branch") == f"refs/heads/{branch}":
                return Path(item["worktree"])
        return None

    def worktree_add(self, path: Path, branch: str, base: str) -> None:
        if self.rev(branch):
            self.run("worktree", "add", "--quiet", str(path), branch)
        else:
            self.run("worktree", "add", "--quiet", "-b", branch, str(path), base)

    def worktree_remove(self, path: Path) -> None:
        self.run("worktree", "remove", str(path))


def story_branch(card_id: str) -> str:
    return f"story/{card_id}"


def worktree_path(main: Path, card_id: str) -> Path:
    return main.parent / f"{main.name}-wt" / card_id
