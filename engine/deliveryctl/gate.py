"""`deliveryctl gate <id>`: the integration check (CONTRACTS.md §10). It needs only git and
Python, so the CI of a merge request runs it without Claude."""

from __future__ import annotations

from pathlib import Path

from . import cards
from . import verdict as vd
from .core import glob_match
from .gitops import Git
from .verify import story_dir

FORBIDDEN = ["spec/**", "spec.lock", ".delivery/**", ".claude/**", "delivery.toml", "CLAUDE.md",
             "**/CLAUDE.md", "docs/stories/*/work/**"]


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
    out = git.out("log", "--format=%H%x01%(trailers:key=Agent,valueonly,separator=%x2C)%x00",
                  f"{base}..{head}", check=False)
    found = {}
    for entry in out.split("\x00"):
        sha, _, agent = entry.strip().partition("\x01")
        if sha:
            found[sha] = agent.strip()
    return found
