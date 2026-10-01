"""`deliveryctl gate <id>`: the integration check (CONTRACTS.md §10). It needs only git and
Python, so the CI of a merge request runs it without Claude."""

from __future__ import annotations

import re
from pathlib import Path

from . import cards
from . import verdict as vd
from .core import ID_RX, DeliveryError, glob_match
from .gitops import Git, trailer_values
from .verify import story_dir

FORBIDDEN = ["spec/**", "spec.lock", ".delivery/**", ".claude/**", "delivery.toml", "CLAUDE.md",
             "**/CLAUDE.md", "docs/stories/*/work/**"]


def story_of_branch(git: Git, head: str = "HEAD") -> str | None:
    """The story a branch serves: the id whose order.md is the only file of its first commit
    after the merge-base with the target branch (the first rule of the check below). A clone
    that holds the story branch only has no target branch to measure from: the engine's order
    commit in the history of the branch tells the story instead."""
    try:
        base = git.merge_base(head, git.target_ref())
        first = git.first_commit_files(base, head)
    except DeliveryError:
        return _story_of_order_commit(git, head)
    found = re.fullmatch(r"docs/stories/([^/]+)/order\.md", first[0]) if len(first) == 1 else None
    return found.group(1) if found and ID_RX.match(found.group(1)) else None


def _story_of_order_commit(git: Git, head: str) -> str | None:
    """The id of the most recent engine order commit in the history of `head`: subject
    `order <id>`, trailer `Agent: engine`, and `docs/stories/<id>/order.md` as its only file."""
    try:
        commits = git.out("rev-list", "-E", "--grep=^order ", head).split()
        for commit in commits:
            subject = git.out("log", "-1", "--format=%s", commit)
            found = re.fullmatch(r"order (\S+)", subject.strip())
            if not found or not ID_RX.match(found.group(1)):
                continue
            if "engine" not in trailer_values(git.out("log", "-1", "--format=%B", commit), "Agent"):
                continue
            files = git.out("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit).split("\n")
            if files == [f"docs/stories/{found.group(1)}/order.md"]:
                return found.group(1)
    except DeliveryError:
        pass
    return None


def check(git: Git, card_id: str, base: str | None = None, head: str = "HEAD") -> list[str]:
    problems: list[str] = []
    base = base or git.merge_base(head, git.target_ref())
    own = story_dir(card_id) + "/"

    first = git.first_commit_files(base, head)
    if first != [own + "order.md"]:
        problems.append(f"the first commit of the branch must add {own}order.md only (found: {first or 'no commit'})")
    report = git.show(head, own + "report.md")
    outcome = vd.outcome(report)
    if not outcome or outcome[0] != "done":
        problems.append(f"{own}report.md does not end with 'Outcome: done'")

    tree = git.code_tree(head)
    authors = agents(git, base, head)
    for name, kind, expected in (("verification.md", "verification", "pass"), ("review.md", "review", "yes")):
        parsed = vd.parse(git.show(head, own + name), kind)
        if not parsed:
            problems.append(f"{own}{name}: no verdict")
            continue
        problems += [f"{own}{name}: {p}" for p in parsed.problems]
        commit = git.last_commit_of(own + name, base, head)
        agent = authors.get(commit or "", "")
        if agent != vd.AUTHORS[kind]:
            problems.append(f"{own}{name}: last committed with 'Agent: {agent or 'none'}', "
                            f"expected 'Agent: {vd.AUTHORS[kind]}'")
        if parsed.verdict and parsed.verdict != expected:
            problems.append(f"{own}{name}: verdict is '{parsed.verdict}', expected '{expected}'")
        if parsed.tree and parsed.tree != tree:
            problems.append(f"{own}{name}: Tree {parsed.tree[:12]} is not the current code tree {tree[:12]}")
        for path in parsed.evidence:
            if not git.exists(head, path):
                problems.append(f"{own}{name}: Evidence '{path}' is not in the tree")

    problems += diff_problems(git, card_id, base, head)
    return problems


def diff_problems(git: Git, card_id: str, base: str, head: str) -> list[str]:
    """What the diff base...head may not touch (points 4 and 5 of §10): the integration check
    and the reception of cloud commits (§9) share these rules."""
    problems: list[str] = []
    own = story_dir(card_id) + "/"
    for status, path in git.diff_status(base, head):
        if path.startswith("docs/stories/") and not path.startswith(own):
            problems.append(f"touches another story's folder: {path}")
        elif glob_match(path, FORBIDDEN):
            problems.append(f"touches a protected path: {path}")
        elif path.startswith(cards.BACKLOG + "/"):
            if status != "A":
                problems.append(f"changes an existing card: {path} (cards change by their own merge request)")
                continue
            card = cards.parse(Path(path), git.show(head, path) or "")
            if card.kind != "anomaly" or card.status != "to-triage":
                problems.append(f"adds a card that is not an anomaly to triage: {path}")
    return problems


def agents(git: Git, base: str, head: str = "HEAD") -> dict[str, str]:
    """The 'Agent:' trailer of each commit of base..head (several are joined by commas)."""
    return trailers(git, base, head, "Agent")


def trailers(git: Git, base: str, head: str, key: str) -> dict[str, str]:
    """The value of the trailer `key` of each commit of base..head ('' when absent; several
    values are joined by commas)."""
    out = git.out("log", "--format=%H%x01%B%x00", f"{base}..{head}", check=False)
    found = {}
    for entry in out.split("\x00"):
        sha, _, message = entry.strip().partition("\x01")
        if sha:
            found[sha] = ",".join(trailer_values(message, key))
    return found
