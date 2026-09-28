"""Qualification of an increment (CONTRACTS.md §15): a worktree per increment, the plan and
report formats, the throwaway runner session, and the merge request whose approval by the
decision owner is the verdict."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from . import config, roles, window
from . import frontmatter as fm
from . import verdict as vd
from .config import Config
from .core import (EXIT_ERROR, EXIT_OK, EXIT_PRECONDITION, EXIT_RED, eprint, fail, main_root,
                   repo_root, require_human)
from .forge import Forge
from .gitops import Git, worktree_path

ROLE = "qualification-runner"
TEMPLATES = Path(__file__).resolve().parents[2] / "templates" / "qualification"
PLAN = "qualification/plan.md"
ORDER = "qualification/order.md"
WORK = "qualification/work/"
ORDER_FILLED = ("Objective", "Controls to run", "Environment")
RESULTS = ("pass", "fail", "blocked", "not-run")
INCR_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,40}$")
CONTROL_START_RX = re.compile(r"^###\s+Q(\d+)")
CONTROL_RX = re.compile(r"^###\s+Q(\d+)\s+[—–-]+\s+(.+?)\s+\[(read|run)(,\s*negative)?\]\s*$")
FIELD_RX = re.compile(r"^(Targets|Touches|Do|Expect):\s*(.*?)\s*$")
HEADER_RX = re.compile(r"^(Tree|Spec|Env):\s*(.*?)\s*$")
NOT_COVERED_RX = re.compile(r"^not covered\s*(?:[—–-]+\s*(.*))?$", re.IGNORECASE)
Q_RX = re.compile(r"\bQ(\d+)\b")
SEPARATOR_RX = re.compile(r"^:?-+:?$")


def branch_of(incr: str) -> str:
    return f"qualification/{incr}"


def report_path(incr: str) -> str:
    return f"qualification/reports/{incr}.md"


def check_increment(value: str) -> str:
    if not INCR_RX.match(value or "") or ".." in value or value.endswith((".", ".lock")):
        fail(EXIT_ERROR, f"invalid increment '{value}' (letters, digits, dots and dashes, e.g. 0.2.0)")
    return value


# -- open -----------------------------------------------------------------------------------
def _spec(wt: Path) -> str:
    lock = wt / "spec.lock"
    if lock.exists():
        try:
            data = tomllib.loads(lock.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            return "spec.lock unreadable"
        return f"{data.get('version', '?')} (commit {str(data.get('commit', ''))[:7]})"
    return "spec/ of this repository" if (wt / "spec").is_dir() else "none"


def _materialize(path: Path, template: str, values: dict) -> bool:
    if path.exists():
        return False
    text = (TEMPLATES / template).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(key, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def open_qualification(cfg: Config, incr: str) -> str:
    """Worktree from the head of the target branch and the skeletons; nothing is committed."""
    if cfg.repo_role == "spec":
        fail(EXIT_PRECONDITION, "qualification runs in an implementation repository (repo_role impl or single)")
    main = Git(cfg.root)
    main.fetch()
    branch = branch_of(incr)
    wt = main.worktree_for(branch)
    if not wt:
        wt = worktree_path(cfg.root, f"qualification-{incr}")
        wt.parent.mkdir(parents=True, exist_ok=True)
        main.worktree_add(wt, branch, main.target_ref())
    git = Git(wt)
    base = git.merge_base("HEAD", git.target_ref())
    values = {"<incr>": incr, "<base>": base, "<tree>": git.code_tree(base), "<spec>": _spec(wt)}
    lines = [f"qualification {incr}: {wt}", f"  branch: {branch} from {git.target_ref()} at {base[:10]}"]
    for name, rel in (("plan", PLAN), ("report", report_path(incr)), ("order", ORDER)):
        made = _materialize(wt / rel, f"{name}.md", values)
        lines.append(f"  {name}: {wt / rel} ({'created' if made else 'existing'})")
    if not git.ok("check-ignore", "-q", WORK + "notes.md"):
        eprint(f"note: {WORK} is not ignored by git: add it to .gitignore")
    lines.append("  nothing is committed: the qualification-lead commits the plan, the report and the order")
    return "\n".join(lines)


# -- run ------------------------------------------------------------------------------------
def order_problems(text: str) -> list[str]:
    try:
        data, body = fm.split(text, ORDER)
    except fm.FrontmatterError as exc:
        return [exc.message]
    problems = []
    if not data.get("base") or str(data["base"]).startswith("<"):
        problems.append("frontmatter 'base' is not filled")
    body = _uncomment(body)
    for name in ORDER_FILLED:
        if not fm.meaningful(fm.section_get(body, name)):
            problems.append(f"section '## {name}' is not filled")
    return problems


def start_runner(cfg: Config, incr: str) -> str:
    wt = Git(cfg.root).worktree_for(branch_of(incr))
    if not wt:
        fail(EXIT_PRECONDITION, f"no worktree for {branch_of(incr)}: run 'deliveryctl qualify open {incr}'")
    order = wt / ORDER
    if not order.exists():
        fail(EXIT_PRECONDITION, f"{ORDER} is missing: 'deliveryctl qualify open {incr}' writes its skeleton")
    problems = order_problems(order.read_text(encoding="utf-8"))
    if problems:
        fail(EXIT_PRECONDITION, f"{ORDER} is not filled:\n  " + "\n  ".join(problems))
    if ORDER in Git(wt).dirty():
        fail(EXIT_PRECONDITION, f"{ORDER} has uncommitted changes: commit it, then run again")
    if not (wt / PLAN).exists():
        fail(EXIT_PRECONDITION, f"{PLAN} is missing")
    win = window.get(cfg.root)
    if win.role_alive(incr, ROLE):
        fail(EXIT_PRECONDITION, f"a {ROLE} session of {incr} is running")
    spec = roles.launch(cfg, ROLE, wt, incr, roles.PROMPTS[ROLE].format(id=incr), headless=win.headless)
    info = win.start_role(incr, ROLE, spec)
    where = f", log {info['log']}" if info.get("log") else ""
    return f"{ROLE} started for {incr} (window {win.name}{where}); results go to {report_path(incr)}"


# -- lint -----------------------------------------------------------------------------------
def _uncomment(text: str) -> str:
    """HTML comments blanked out, line numbers kept."""
    return re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)


def _numbered(text: str) -> list[tuple[int, str]]:
    """Lines outside comments and code fences, with their 1-based numbers."""
    out, fence = [], False
    for no, line in enumerate(_uncomment(text).splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = not fence
        elif not fence:
            out.append((no, line.rstrip()))
    return out


def _placeholder(value: str) -> bool:
    value = value.strip()
    return value.startswith("<") and value.endswith(">")


def _blank(value: str) -> bool:
    return not value.strip() or _placeholder(value)


def _tables(lines: list[tuple[int, str]]) -> list[tuple[int, list[str]]]:
    """Data rows of the markdown tables among the lines (header and separator dropped)."""
    blocks, cur = [], []
    for no, line in lines:
        if line.lstrip().startswith("|"):
            cur.append((no, [c.strip() for c in line.strip().strip("|").split("|")]))
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    rows = []
    for block in blocks:
        if len(block) > 1 and all(SEPARATOR_RX.match(c) for c in block[1][1] if c):
            block = block[2:]
        rows += block
    return rows


def lint_plan(text: str) -> tuple[list[tuple[int, str]], dict]:
    """Problems of plan.md and its controls {number: line}."""
    problems, controls, surface, surface_at = [], {}, [], None
    section, current = "", None

    def close(ctrl):
        if not ctrl:
            return
        problems.extend((ctrl["line"], f"Q{ctrl['n']}: missing '{key}:' line")
                        for key in ("Targets", "Do", "Expect") if key not in ctrl["fields"])
        problems.extend((at, f"Q{ctrl['n']}: '{key}:' is not filled")
                        for key, (at, value) in ctrl["fields"].items() if _blank(value))

    for no, line in _numbered(text):
        if line.startswith("## ") or line.startswith("### "):
            close(current)
            current = None
        if line.startswith("## "):
            section = line[3:].strip()
            if section.startswith("Surface") and surface_at is None:
                surface_at = no
            continue
        start = CONTROL_START_RX.match(line)
        if start:
            match, n = CONTROL_RX.match(line), int(start.group(1))
            if not match:
                problems.append((no, "control heading must read '### Q<n> — <title>   [read|run]' "
                                     "(', negative' optional)"))
            elif _placeholder(match.group(2)):
                problems.append((no, f"Q{n}: title is not filled"))
            if n in controls:
                problems.append((no, f"Q{n} is already used at line {controls[n]}"))
            else:
                controls[n] = no
            current = {"n": n, "line": no, "fields": {}}
            continue
        if section.startswith("Surface"):
            surface.append((no, line))
        field = FIELD_RX.match(line.strip())
        if current and field and field.group(1) not in current["fields"]:
            current["fields"][field.group(1)] = (no, field.group(2))
    close(current)

    if surface_at is None:
        problems.append((1, "missing section '## Surface'"))
        return problems, controls
    rows = _tables(surface)
    if not rows:
        problems.append((surface_at, "'## Surface' has no table row: one row per entry point"))
    for no, cells in rows:
        if any(_placeholder(c) for c in cells):
            problems.append((no, "Surface row is not filled"))
            continue
        uncovered = next((m for m in (NOT_COVERED_RX.match(c) for c in cells) if m), None)
        refs = [int(n) for c in cells for n in Q_RX.findall(c)]
        if uncovered and _blank(uncovered.group(1) or ""):
            problems.append((no, "'not covered' needs its reason: 'not covered — <reason>'"))
        elif not uncovered and not refs:
            problems.append((no, "entry point without a control: name a Q<n> or write 'not covered — <reason>'"))
        problems += [(no, f"Q{n} is not a control of the plan") for n in refs if n not in controls]
    return problems, controls


def lint_report(text: str, controls: dict, expected_tree: str | None = None,
                git: Git | None = None) -> list[tuple[int, str]]:
    problems = []
    lines = _numbered(text)
    body = list(lines)
    while body and not body[-1][1].strip():
        body.pop()
    last = body[-1][0] if body else 1
    block_at = None
    while body and vd.LINE_RX.match(body[-1][1].strip()):
        block_at = body.pop()[0]

    header, sections, current = {}, {}, None
    for no, line in body:
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = (no, [])
        elif current:
            sections[current][1].append((no, line))
        else:
            match = HEADER_RX.match(line.strip())
            if match and match.group(1) not in header:
                header[match.group(1)] = (no, match.group(2))
    for key in ("Tree", "Spec", "Env"):
        if key not in header:
            problems.append((1, f"missing header line '{key}:'"))
        elif _blank(header[key][1]):
            problems.append((header[key][0], f"header '{key}:' is not filled"))
    tree_at, tree = header.get("Tree", (1, ""))
    if tree and not _blank(tree):
        if not vd.TREE_RX.match(tree):
            problems.append((tree_at, "header 'Tree:' is not a 40-character code tree id"))
        elif expected_tree and tree != expected_tree:
            problems.append((tree_at, f"header 'Tree:' is not the code tree of the qualified commit ({expected_tree})"))

    for name in ("Read", "Run"):
        found = next((h for h in sections if h == name or h.startswith(name + " ")), None)
        if found is None:
            problems.append((1, f"missing section '## {name}'"))
        elif not fm.meaningful("\n".join(line for _, line in sections[found][1])):
            problems.append((sections[found][0], f"section '## {name}' is empty: say why"))

    listed = set()
    for no, cells in _tables(body):
        if any(_placeholder(c) for c in cells):
            problems.append((no, "table row is not filled"))
            continue
        if "/tmp/" in " ".join(cells):
            problems.append((no, "a proof is never a path under /tmp"))
        match = re.match(r"^Q(\d+)$", cells[0])
        if not match:
            continue
        listed.add(int(match.group(1)))
        if (cells[2].lower() if len(cells) > 2 else "") not in RESULTS:
            problems.append((no, f"Q{match.group(1)}: result must be one of {', '.join(RESULTS)}"))
    results_at = next((at for h, (at, _) in sections.items() if h.startswith("Results")), 1)
    problems += [(results_at, f"Q{n} of the plan has no result row") for n in sorted(set(controls) - listed)]

    parsed = vd.parse(_uncomment(text), "qualification")
    at = block_at or last
    if not parsed:
        return problems + [(last, "no verdict block at the end (Verdict, Tree, Command, Result, By)")]
    problems += [(at, p) for p in parsed.problems]
    problems += [(at, f"verdict '{k.title()}:' is not filled") for k in ("command", "result")
                 if _placeholder(getattr(parsed, k))]
    if parsed.by and parsed.by != "qualification-lead":
        problems.append((at, "a qualification verdict is proposed by: qualification-lead"))
    if parsed.tree and tree and vd.TREE_RX.match(tree) and parsed.tree != tree:
        problems.append((at, "verdict 'Tree:' differs from the header 'Tree:'"))
    for path in parsed.evidence:
        if git and (not (git.cwd / path).exists() or git.ok("check-ignore", "-q", path)):
            problems.append((at, f"Evidence '{path}' is not a committed path of the worktree"))
    return problems


def lint_files(root: Path, incr: str, expected_tree: str | None = None) -> list[str]:
    root = Path(root)
    plan = root / PLAN
    if not plan.exists():
        return [f"{PLAN}:1: missing: run 'deliveryctl qualify open {incr}'"]
    problems, controls = lint_plan(plan.read_text(encoding="utf-8"))
    out = [f"{PLAN}:{no}: {msg}" for no, msg in sorted(problems, key=lambda p: p[0])]
    report = root / report_path(incr)
    if report.exists():
        found = lint_report(report.read_text(encoding="utf-8"), controls, expected_tree, Git(root))
        out += [f"{report_path(incr)}:{no}: {msg}" for no, msg in sorted(found, key=lambda p: p[0])]
    return out


def lint(cfg: Config, incr: str) -> tuple[Path, list[str]]:
    """Lint the qualification worktree when it exists (the report Tree must be the code tree
    of the commit it branched from), else the current checkout (format only)."""
    wt = Git(cfg.root).worktree_for(branch_of(incr))
    if not wt:
        root = repo_root()
        return root, lint_files(root, incr)
    git = Git(wt)
    return wt, lint_files(wt, incr, git.code_tree(git.merge_base("HEAD", git.target_ref())))


# -- submit ---------------------------------------------------------------------------------
def submit(cfg: Config, incr: str) -> str:
    require_human("deliveryctl qualify submit")
    branch = branch_of(incr)
    wt = Git(cfg.root).worktree_for(branch)
    if not wt:
        fail(EXIT_PRECONDITION, f"no worktree for {branch}")
    git = Git(wt)
    pending = git.dirty()
    if pending:
        fail(EXIT_PRECONDITION, "uncommitted changes in the qualification worktree:\n  " + "\n  ".join(pending))
    body = git.show("HEAD", report_path(incr))
    if body is None:
        fail(EXIT_PRECONDITION, f"{report_path(incr)} is not committed on {branch}")
    _, problems = lint(cfg, incr)
    if problems:
        fail(EXIT_RED, "qualification lint is red:\n  " + "\n  ".join(problems))
    if cfg.forge == "none":
        return f"forge = none: {branch} stays local; the decision owner merges it (git merge --no-ff {branch})"
    return Forge(cfg, git).open_branch(branch, f"Recette {incr} ({branch})", body)


def close(cfg: Config, incr: str) -> str:
    """Remove the qualification worktree and its window; the branch stays (its report may still
    be under review). Refused while a runner session is running."""
    main = Git(cfg.root)
    wt = main.worktree_for(branch_of(incr))
    if not wt:
        return f"no worktree for qualification {incr}"
    win = window.get(cfg.root)
    if win.role_alive(incr, ROLE):
        fail(EXIT_PRECONDITION, f"a {ROLE} session of {incr} is still running")
    win.close_story(incr)
    main.run("worktree", "remove", "--force", str(wt))
    return f"closed qualification {incr} (branch {branch_of(incr)} kept)"


def main(args) -> int:
    incr = check_increment(args.increment)
    cfg = config.load(main_root())
    if args.action == "open":
        print(open_qualification(cfg, incr))
    elif args.action == "run":
        print(start_runner(cfg, incr))
    elif args.action == "lint":
        _, problems = lint(cfg, incr)
        for line in problems:
            print(line)
        print("qualification: " + ("red" if problems else "green"))
        return EXIT_RED if problems else EXIT_OK
    elif args.action == "submit":
        print(submit(cfg, incr))
    elif args.action == "close":
        print(close(cfg, incr))
    return EXIT_OK
