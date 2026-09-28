"""Backlog cards: loading, readiness checks, dependency order (CONTRACTS.md §5)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter as fm
from .config import RISKS
from .core import EXIT_ERROR, EXIT_RED, ID_RX, DeliveryError, fail
from .gitops import Git

BACKLOG = "backlog"
KINDS = ("story", "task", "anomaly")
STATUSES = ("draft", "ready", "to-triage", "deferred", "dropped")
KEYS = ("id", "kind", "title", "status", "depends_on", "risks", "spec", "code", "show_plan", "found")
FILE_RX = re.compile(r"^([sta][0-9]{3,4})-[a-z0-9][a-z0-9-]*\.md$")
MERGE_SUBJECT_RX = re.compile(r"^Merge\b.*?\bstory/([sta][0-9]{3,4})\b")
SPEC_RX = re.compile(r"^s[0-9]{3,4}$")
NOT_TESTED_RX = re.compile(r"^\s*[-*]?\s*Not tested by this card\s*:", re.MULTILINE)
TITLE_REQUIRED = "title: a short title is required"
LONG_TITLE = 60             # characters: past it, `cards lint` notes the title, without refusing it


@dataclass
class Card:
    id: str
    kind: str
    title: str
    status: str
    depends_on: list
    risks: list
    spec: str
    code: bool
    show_plan: bool
    found: str
    path: Path
    body: str
    problems: list = field(default_factory=list)

    @property
    def rel(self) -> str:
        return f"{BACKLOG}/{self.path.name}"


def parse(path: Path, text: str, allowed: tuple = RISKS) -> Card:
    problems = []
    try:
        data, body = fm.split(text, str(path))
    except fm.FrontmatterError as exc:
        data, body = {}, text
        problems.append(exc.message)
    for key in data:
        if key not in KEYS:
            problems.append(f"unknown key '{key}'")
    match = FILE_RX.match(path.name)
    card_id = str(data.get("id") or "")
    if not match:
        problems.append("file name must be <id>-<slug>.md (lowercase slug)")
    elif match.group(1) != card_id:
        problems.append(f"id '{card_id}' does not match the file name")
    if not ID_RX.match(card_id):
        problems.append(f"invalid id '{card_id}'")
    kind = data.get("kind") or ""
    if kind not in KINDS:
        problems.append(f"kind must be one of {', '.join(KINDS)}")
    elif card_id and card_id[0] != kind[0]:
        problems.append(f"a {kind} id starts with '{kind[0]}'")
    status = data.get("status") or ""
    if status not in STATUSES:
        problems.append(f"status must be one of {', '.join(STATUSES)}")
    deps = data.get("depends_on") or []
    declared = data.get("risks") or []
    if not isinstance(deps, list):
        problems.append("depends_on must be a list")
        deps = []
    if not isinstance(declared, list):
        problems.append("risks must be a list")
        declared = []
    declared = [str(r) for r in declared]
    for risk in declared:
        if risk not in allowed:
            problems.append(f"unknown risk '{risk}' (declare it under [levers] reinforced_risks)")
    code = data.get("code", True)
    if not isinstance(code, bool):
        problems.append("code must be true or false")
        code = True
    show_plan = data.get("show_plan", False)
    if not isinstance(show_plan, bool):
        problems.append("show_plan must be true or false")
        show_plan = False
    spec = str(data.get("spec") or "")
    if spec and not SPEC_RX.match(spec):
        problems.append(f"spec must be a spec story id like s004, got '{spec}'")
    title = " ".join(str(data.get("title") or "").split())
    if not title:
        problems.append(TITLE_REQUIRED)
    return Card(
        id=card_id, kind=kind, title=title, status=status,
        depends_on=[str(d) for d in deps], risks=declared,
        spec=spec, code=code, show_plan=show_plan,
        found=str(data.get("found") or ""),
        path=path, body=body, problems=problems,
    )


def load_all(root: Path, risks: tuple = RISKS) -> list[Card]:
    folder = Path(root) / BACKLOG
    if not folder.is_dir():
        return []
    return [parse(p, p.read_text(encoding="utf-8"), risks) for p in sorted(folder.glob("*.md"))]


def load_from_rev(git: Git, rev: str, risks: tuple = RISKS) -> list[Card]:
    """Cards as they are on a revision (the run reads the target branch, not the checkout)."""
    proc = git.run("ls-tree", "--name-only", f"{rev}:{BACKLOG}", check=False)
    if proc.returncode != 0:
        return []
    cards = []
    for name in sorted(proc.stdout.split()):
        if name.endswith(".md"):
            text = git.show(rev, f"{BACKLOG}/{name}") or ""
            cards.append(parse(Path(BACKLOG) / name, text, risks))
    return cards


# -- how a card is named for a human (CONTRACTS.md §5) ----------------------------------------
_TITLES: dict[str, dict[str, str]] = {}


def label(card_id: str, title: str = "") -> str:
    """'<id> : <short title>'; the identifier alone when the title is unknown or a placeholder."""
    title = " ".join(str(title or "").split())
    return f"{card_id} : {title}" if fm.meaningful(title) else card_id


def titles(git: Git, rev: str | None = None) -> dict[str, str]:
    """Titles of the cards of a revision (the target branch by default), by id. Cached per
    process by the tree of backlog/, so that naming a card costs one git call; empty when the
    backlog cannot be read (no target branch, no backlog)."""
    try:
        rev = rev or git.target_ref()
        tree = git.run("rev-parse", "--verify", "--quiet", f"{rev}:{BACKLOG}", check=False).stdout.strip()
        if tree and tree not in _TITLES:
            names = git.out("ls-tree", "--name-only", tree, check=False).split()
            found = [parse(Path(BACKLOG) / n, git.show(tree, n) or "") for n in names if n.endswith(".md")]
            _TITLES[tree] = {c.id: c.title for c in found if c.id}
    except DeliveryError:
        return {}
    return _TITLES.get(tree, {})


def label_of(git: Git, card_id: str) -> str:
    """Label of a card read on the target branch; the identifier alone when it is not there."""
    return label(card_id, titles(git).get(card_id, ""))


def labels(ids, known: dict[str, str]) -> str:
    """Labels of several cards; '; ' between them, since a title may hold a comma."""
    return "; ".join(label(i, known.get(i, "")) for i in ids)


def find(cards: list[Card], card_id: str) -> Card:
    for card in cards:
        if card.id == card_id:
            return card
    fail(EXIT_ERROR, f"card '{card_id}' not found in {BACKLOG}/")


def readiness(card: Card) -> list[str]:
    """What prevents a card from being executed by a mid-range agent without questions."""
    problems = []
    if not fm.meaningful(fm.section_get(card.body, "Objective")):
        problems.append("'## Objective' is empty")
    if not fm.meaningful(fm.section_get(card.body, "Context and scope")):
        problems.append("'## Context and scope' is empty")
    if card.code:
        oracle = fm.section_get(card.body, "Oracle")
        if not fm.meaningful(oracle):
            problems.append("'## Oracle' is required for a card with code")
        elif not NOT_TESTED_RX.search(oracle or ""):
            problems.append("'## Oracle' needs a 'Not tested by this card:' line")
    if card.kind == "story" and not card.spec:
        problems.append("a story card names its spec story ('spec: s004')")
    if card.title and not fm.meaningful(card.title):
        problems.append(TITLE_REQUIRED)
    return problems


def lint(cards: list[Card]) -> list[tuple[str, str]]:
    """(card id or file, problem) for every structural or readiness problem."""
    out = []
    ids = {}
    for card in cards:
        where = card.id or card.path.name
        for problem in card.problems:
            out.append((where, problem))
        if card.id in ids:
            out.append((where, f"duplicate id (also {ids[card.id]})"))
        ids[card.id] = card.path.name
        if card.kind == "anomaly" and not card.found:
            out.append((where, "an anomaly says where it was found ('found: <where>@<commit>')"))
        if card.status == "ready":
            out += [(where, p) for p in readiness(card)]
    for card in cards:
        for dep in card.depends_on:
            if dep not in ids:
                out.append((card.id, f"depends on unknown card '{dep}'"))
    known = {c.id: c.title for c in cards}
    for cycle in cycles(cards):
        out.append((cycle[0], "dependency cycle: " + " -> ".join(label(i, known.get(i, "")) for i in cycle)))
    return out


def notes(cards: list[Card]) -> list[tuple[str, str]]:
    """(card id or file, note): remarks that do not make the backlog red."""
    return [(c.id or c.path.name, f"title of {len(c.title)} characters: a short title reads in a few words (3 to 8)")
            for c in cards if len(c.title) > LONG_TITLE]


def where_label(where: str, cards: list[Card]) -> str:
    """The card a lint line is about, by its label; a file name stays as it is."""
    return label(where, next((c.title for c in cards if c.id == where), ""))


def cycles(cards: list[Card]) -> list[list[str]]:
    graph = {c.id: [d for d in c.depends_on] for c in cards}
    found, state, stack = [], {}, []

    def visit(node):
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, []):
            if state.get(dep) == 1:
                found.append(stack[stack.index(dep):] + [dep])
            elif dep in graph and not state.get(dep):
                visit(dep)
        stack.pop()
        state[node] = 2

    for node in graph:
        if not state.get(node):
            visit(node)
    return found


def merged_ids(git: Git, target_ref: str | None = None) -> set[str]:
    """Cards whose story branch reached the target branch (local or remote-tracking): a merge
    subject naming 'story/<id>' or a 'Story: <id>' trailer on the target history."""
    if target_ref is None:
        name = git.target_branch()
        refs = [r for r in (name, f"origin/{name}") if git.rev(r)]
        return set().union(*(merged_ids(git, r) for r in refs)) if refs else set()
    out = git.run("log", "--format=%s%x01%b%x00", target_ref, check=False).stdout
    done = set()
    for entry in out.split("\x00"):
        subject, _, body = entry.strip("\n").partition("\x01")
        if MERGE_SUBJECT_RX.match(subject):
            done.update(MERGE_SUBJECT_RX.match(subject).group(1).split())
        for match in re.finditer(r"\(story/([sta][0-9]{3,4})\)", subject):
            done.add(match.group(1))
        if "Approved-By:" in body:
            for match in re.finditer(r"^Story:\s*([sta][0-9]{3,4})\s*$", body, re.MULTILINE):
                done.add(match.group(1))
    return done

def order(cards: list[Card], done: set[str]) -> list[tuple[Card, list[str]]]:
    """Ready cards not yet done, in dependency order. Each comes with the list of its
    dependencies that are not done yet (empty = it can start now)."""
    by_id = {c.id: c for c in cards}
    pending = [c for c in cards if c.status == "ready" and c.id not in done]
    placed, result = set(), []
    remaining = sorted(pending, key=lambda c: c.id)
    while remaining:
        progress = False
        for card in list(remaining):
            deps = [d for d in card.depends_on if d not in done]
            if all(d in placed or d not in by_id or by_id[d].status != "ready" for d in deps):
                result.append((card, deps))
                placed.add(card.id)
                remaining.remove(card)
                progress = True
        if not progress:
            for card in remaining:
                result.append((card, [d for d in card.depends_on if d not in done]))
            break
    return result


def ensure_clean(cards: list[Card]) -> None:
    problems = lint(cards)
    if problems:
        lines = "\n".join(f"  {where_label(where, cards)} — {problem}" for where, problem in problems)
        fail(EXIT_RED, f"backlog problems:\n{lines}")
