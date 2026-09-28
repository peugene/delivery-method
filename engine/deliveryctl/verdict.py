"""Verdict blocks and Outcome lines (CONTRACTS.md §7)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KEYS = ("Verdict", "Tree", "Command", "Result", "By")
VALUES = {
    "verification": ("pass", "fail"),
    "review": ("yes", "no"),
    "qualification": ("accepted", "accepted-with-reserves", "rejected"),
}
AUTHORS = {"verification": "engine", "review": "story-reviewer"}   # By: line and Agent: trailer
OUTCOMES = ("done", "blocked", "deferred", "plan-ready", "question")
LINE_RX = re.compile(r"^(Verdict|Tree|Command|Result|By|Evidence):\s*(.*?)\s*$")
OUTCOME_RX = re.compile(r"^Outcome:\s*(done|blocked|deferred|plan-ready|question)\b\s*(?:[—–-]+\s*(.*))?$")
TREE_RX = re.compile(r"^[0-9a-f]{40}$")


@dataclass
class Verdict:
    verdict: str = ""
    tree: str = ""
    command: str = ""
    result: str = ""
    by: str = ""
    evidence: list = field(default_factory=list)
    problems: list = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.problems


def parse(text: str | None, kind: str) -> Verdict | None:
    """Parse the trailing verdict block of a file. Returns None when there is no block."""
    if not text:
        return None
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()
    block: list[tuple[str, str]] = []
    for line in reversed(lines):
        match = LINE_RX.match(line.strip())
        if not match:
            break
        block.append((match.group(1), match.group(2)))
    if not block:
        return None
    block.reverse()
    out = Verdict()
    seen = []
    for key, value in block:
        if key == "Evidence":
            out.evidence.append(value)
            continue
        if key in seen:
            out.problems.append(f"duplicate '{key}:' line")
        seen.append(key)
        setattr(out, key.lower(), value)
    order = [k for k in seen if k in KEYS]
    if order != [k for k in KEYS if k in order]:
        out.problems.append("verdict lines out of order (Verdict, Tree, Command, Result, By, Evidence)")
    for key in KEYS:
        if key not in seen:
            out.problems.append(f"missing '{key}:' line")
    if out.verdict and out.verdict not in VALUES[kind]:
        out.problems.append(f"Verdict must be one of {', '.join(VALUES[kind])}, got '{out.verdict}'")
    if out.by and kind in AUTHORS and out.by != AUTHORS[kind]:
        out.problems.append(f"By must be '{AUTHORS[kind]}' for a {kind} verdict, got '{out.by}'")
    if out.tree and not TREE_RX.match(out.tree):
        out.problems.append(f"Tree is not a 40-character hexadecimal id: '{out.tree}'")
    for path in out.evidence:
        if path.startswith("/") or path.startswith("~") or ".." in path.split("/"):
            out.problems.append(f"Evidence outside the repository: '{path}'")
    return out


def render(verdict: str, tree: str, command: str, result: str, by: str, evidence=()) -> str:
    lines = [f"Verdict: {verdict}", f"Tree: {tree}", f"Command: {command}",
             f"Result: {result}", f"By: {by}"]
    lines += [f"Evidence: {path}" for path in evidence]
    return "\n".join(lines) + "\n"


def outcome(text: str | None) -> tuple[str, str] | None:
    """Outcome of a report: the last non-empty line, `Outcome: <value> — <reason>`."""
    if not text:
        return None
    for line in reversed(text.splitlines()):
        if line.strip():
            match = OUTCOME_RX.match(line.strip())
            return (match.group(1), (match.group(2) or "").strip()) if match else None
    return None
