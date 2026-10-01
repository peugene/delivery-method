"""Specification verbs (CONTRACTS.md §14): lint, release, sync, verify.

Conventions checked by `spec lint`, also stated in templates/spec/story.md:
- an extension is a top-level list item of `## Extensions`, labelled by its main-flow step and a
  letter: `- 2a. <condition>: <what happens>`;
- a criterion is one line of `## Acceptance criteria`:
  `AC<n> @main|@ext-<label> — Given … When … Then …`; numbers are never reused;
- a test covers a criterion with `@<id>-ac<n>` in its title, and carries `@<id>` in its title or
  in a `test.describe` title of the same file.
Correctness rules apply to every story. Completeness rules (full schema, a criterion per
extension, a test per criterion) apply to `ready` stories, so that the drafts of a later
increment never block a release.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import VERSION
from . import config
from . import frontmatter as fm
from .core import (EXIT_ERROR, EXIT_OK, EXIT_PRECONDITION, EXIT_RED, fail, repo_root,
                   require_human, require_local)
from .gitops import Git, trailer_values

SPEC = "spec"
STORIES = f"{SPEC}/stories"
LOCK = "spec.lock"
CONFORMANCE = "docs/conformance.md"
STORY_KEYS = ("id", "title", "status")
STATUSES = ("draft", "ready")
SECTIONS = ("Business rules", "Main flow", "Extensions", "Acceptance criteria", "UI contract",
            "Outcomes", "Out of scope", "Open questions")
FILLED = ("Business rules", "Main flow", "Acceptance criteria")
RULES = ("schema", "neutrality", "extension", "coverage", "orphan-tag", "test-tag")
LEVELS = ("patch", "minor", "major")
TEST_MODIFIERS = ("", ".only", ".skip", ".fixme", ".fail", ".slow")

FILE_RX = re.compile(r"^(s[0-9]{3,4})-[a-z0-9][a-z0-9-]*\.md$")
H2_RX = re.compile(r"^## (.+?)\s*$")
EXT_RX = re.compile(r"^[-*]\s+([0-9]+[a-z])[.:]\s+\S")
AC_START_RX = re.compile(r"^(?:[-*]\s+)?AC[0-9]")
AC_RX = re.compile(r"^(?:[-*]\s+)?AC([0-9]+)\s+@(main|ext-[0-9]+[a-z])\s+[—–-]+\s+"
                   r"(Given\b.+\bWhen\b.+\bThen\b.+)$")
EXEMPT_RX = re.compile(r"^\s*(?:[-*]\s+)?lint-exempt:\s*(\S+)\s*(?:[—–-]+\s*(.*?))?\s*$")
TITLE_RX = re.compile(r"\btest((?:\.[A-Za-z]+)*)\s*\(\s*(['\"`])((?:\\.|(?!\2).)*?)\2")
TAG_AC_RX = re.compile(r"@(s[0-9]{3,4})-ac([0-9]+)(?![\w-])")
TAG_ID_RX = re.compile(r"@(s[0-9]{3,4})(?![\w-])")
KEY_SPAN_RX = re.compile(r"`[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+`")
HTTP_CODE_RX = re.compile(r"(?<!\w)(?:HTTP|code|status)\s*[1-5][0-9]{2}(?!\w)", re.IGNORECASE)
SEMVER_RX = re.compile(r"^([0-9]+)\.([0-9]+)\.([0-9]+)$")
SPEC_TRAILER_RX = re.compile(r"^Spec:\s*(s[0-9]{3,4})@(\S+?)(?:#([0-9a-f]{7,40}))?\s*$", re.MULTILINE)

# A lowercase entry matches any case and a plural in -s; an entry with a capital matches as is.
LEXICON = (
    "SQL", "NoSQL", "PostgreSQL", "Postgres", "MySQL", "SQLite", "MongoDB", "Redis",
    "Elasticsearch", "Supabase", "Firebase", "database", "base de données", "bases de données",
    "table", "column", "colonne", "primary key", "foreign key", "clé primaire", "clé étrangère",
    "Java", "Kotlin", "Python", "JavaScript", "TypeScript", "PHP", "C#", ".NET", "Node.js",
    "React", "Angular", "Vue.js", "Svelte", "Next.js", "Nuxt", "Spring", "Django", "Ruby on Rails",
    "Laravel", "Ktor", "HTMX", "Thymeleaf", "jQuery",
    "REST", "GraphQL", "gRPC", "SOAP", "JSON", "XML", "YAML", "HTTP", "API", "endpoint",
    "microservice", "backend", "back-end", "frontend", "front-end", "webhook", "WebSocket", "SSE",
    "cron", "JWT", "OAuth", "ORM", "CSS", "HTML", "localStorage", "UUID", "Docker", "Kubernetes",
    "AWS", "Azure", "Vercel", "status code",
)


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    message: str
    story: str = ""

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.message}"


@dataclass
class Story:
    id: str
    path: str
    status: str = "draft"
    scan: list = field(default_factory=list)        # (line, text) checked for neutrality
    lines: list = field(default_factory=list)       # (line, section, text) of the body
    headings: dict = field(default_factory=dict)    # section -> line of its first heading
    order: list = field(default_factory=list)       # sections in the order they appear
    criteria: dict = field(default_factory=dict)    # n -> (line, label, text)
    extensions: dict = field(default_factory=dict)  # label -> line
    exempt: dict = field(default_factory=dict)      # rule -> reason

    def content(self, section: str) -> list[str]:
        return [text for _, sec, text in self.lines if sec == section]


# -- lint ------------------------------------------------------------------------------------

def _section(heading: str) -> str:
    for name in SECTIONS:
        if heading == name or heading.startswith(name + " "):
            return name
    return heading


def _body_start(lines: list[str]) -> int:
    if lines and lines[0].strip() == "---":
        for n in range(1, len(lines)):
            if lines[n].strip() == "---":
                return n + 1
    return 0


def parse_story(rel: str, text: str) -> tuple[Story, list[Finding]]:
    match = FILE_RX.match(rel.rsplit("/", 1)[-1])
    story = Story(id=match.group(1) if match else "", path=rel)
    found: list[Finding] = []

    def schema(line: int, message: str) -> None:
        found.append(Finding(rel, line, "schema", message, story.id))

    if not match:
        schema(1, "file name must be s<nnn>-<slug>.md")
    try:
        data, _ = fm.split(text, "frontmatter")
    except fm.FrontmatterError as exc:
        data = {}
        schema(1, exc.message)
    if data.get("status") in STATUSES:
        story.status = data["status"]
    else:
        schema(1, "status must be draft or ready")
    if match and str(data.get("id") or "") != story.id:
        schema(1, f"id must be '{story.id}', as in the file name")
    if not data.get("title"):
        schema(1, "title is required")
    if story.status == "ready":
        for key in data:
            if key not in STORY_KEYS:
                schema(1, f"unknown frontmatter key '{key}'")
    lines = text.splitlines()
    start = _body_start(lines)
    section, fence = "", False
    for n, line in enumerate(lines, start=1):
        exempt = EXEMPT_RX.match(line)
        if exempt:
            rule, reason = exempt.group(1), (exempt.group(2) or "").strip()
            if rule not in RULES:
                schema(n, f"lint-exempt names an unknown rule '{rule}' ({', '.join(RULES)})")
            elif not reason:
                schema(n, "lint-exempt needs a reason: 'lint-exempt: <rule> — <reason>'")
            else:
                story.exempt[rule] = reason
            continue
        if line.strip() != "---":
            story.scan.append((n, line))
        if n <= start:
            continue
        if line.lstrip().startswith("```"):
            fence = not fence
        heading = None if fence else H2_RX.match(line)
        if heading:
            section = _section(heading.group(1))
            story.headings.setdefault(section, n)
            story.order.append(section)
            continue
        story.lines.append((n, section, line))
        stripped = line.strip()
        ext = EXT_RX.match(line) if section == "Extensions" else None
        if ext:
            if ext.group(1) in story.extensions:
                schema(n, f"extension {ext.group(1)} is listed twice")
            story.extensions.setdefault(ext.group(1), n)
        elif section == "Acceptance criteria" and AC_START_RX.match(stripped):
            crit = AC_RX.match(stripped)
            if not crit:
                schema(n, "a criterion reads 'AC<n> @main|@ext-<label> — Given … When … Then …'")
            elif int(crit.group(1)) in story.criteria:
                schema(n, f"AC{crit.group(1)} is defined twice")
            else:
                story.criteria[int(crit.group(1))] = (n, crit.group(2), " ".join(crit.group(3).split()))
    return story, found


def _is_none(texts: list[str]) -> bool:
    kept = [t.strip().lstrip("-*").strip() for t in texts]
    return not fm.meaningful("\n".join(k for k in kept if k.lower().rstrip(".") != "none"))


def _ready_schema(story: Story) -> list[Finding]:
    out = []

    def schema(line: int, message: str) -> None:
        out.append(Finding(story.path, line, "schema", message, story.id))

    for name in SECTIONS:
        if name not in story.headings:
            schema(1, f"missing section '## {name}'")
    known = [s for s in story.order if s in SECTIONS]
    if known != sorted(known, key=SECTIONS.index):
        schema(story.headings[known[0]], "sections out of order: " + ", ".join(SECTIONS))
    for name in FILLED:
        if name in story.headings and not fm.meaningful("\n".join(story.content(name))):
            schema(story.headings[name], f"'## {name}' is empty")
    if "Open questions" in story.headings and not _is_none(story.content("Open questions")):
        schema(story.headings["Open questions"], "a ready story has no open question (empty or 'none')")
    if not any(label == "main" for _, label, _ in story.criteria.values()):
        schema(story.headings.get("Acceptance criteria", 1), "a ready story has at least one @main criterion")
    return out


def _extensions(story: Story) -> list[Finding]:
    out, used = [], set()
    for n, (line, label, _) in sorted(story.criteria.items()):
        if label.startswith("ext-"):
            used.add(label[4:])
            if label[4:] not in story.extensions:
                out.append(Finding(story.path, line, "extension",
                                   f"AC{n} names extension {label[4:]}, absent from '## Extensions'", story.id))
    if story.status == "ready":
        for label, line in story.extensions.items():
            if label not in used:
                out.append(Finding(story.path, line, "extension",
                                   f"extension {label} has no criterion (@ext-{label})", story.id))
    return out


def _term_rx(term: str) -> re.Pattern:
    lower = term == term.lower()
    body = re.escape(term).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<!\w){body}{'s?' if lower else ''}(?!\w)", re.IGNORECASE if lower else 0)


def lexicon(settings: dict) -> list[re.Pattern]:
    neutral = settings.get("neutrality") or {}
    allow = {w.lower() for w in neutral.get("allow", [])}
    terms = [t for t in LEXICON if t.lower() not in allow] + list(neutral.get("extra", []))
    out = [] if "http status code" in allow else [HTTP_CODE_RX]
    return out + [_term_rx(t) for t in dict.fromkeys(terms)]


def _neutral_text(line: str, section: str) -> str:
    """The line without label keys and, in the UI contract, without the accessible role."""
    text = KEY_SPAN_RX.sub(lambda m: " " * len(m.group(0)), line)
    cells = text.split("|")
    if section == "UI contract" and text.lstrip().startswith("|") and len(cells) > 3:
        cells[2] = " " * len(cells[2])
    return "|".join(cells)


def _neutrality(story: Story, terms: list[re.Pattern]) -> list[Finding]:
    out, sections = [], {n: sec for n, sec, _ in story.lines}
    for n, line in story.scan:
        text, spans = _neutral_text(line, sections.get(n, "")), []
        for rx in terms:
            for m in rx.finditer(text):
                if any(m.start() < end and start < m.end() for start, end in spans):
                    continue
                spans.append((m.start(), m.end()))
                out.append(Finding(story.path, n, "neutrality",
                                   f"technology word '{m.group(0)}': say what the user observes "
                                   "(a product word goes to [neutrality] allow)", story.id))
    return out


def scan_titles(root: Path) -> list[tuple[str, int, str, str]]:
    """(path, line, 'test' | 'describe', title) of every Playwright title in spec/acceptance."""
    base, out = root / SPEC / "acceptance", []
    for path in sorted(base.rglob("*.spec.ts")) if base.is_dir() else []:
        if "node_modules" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in TITLE_RX.finditer(line):
                mods = m.group(1)
                kind = "describe" if mods.startswith(".describe") else "test" if mods in TEST_MODIFIERS else ""
                if kind:
                    out.append((rel, n, kind, m.group(3)))
    return out


def _tests(titles: list, stories: dict) -> list[Finding]:
    out, covered, carried = [], set(), {}
    for rel, _, kind, title in titles:
        if kind == "describe":
            carried.setdefault(rel, set()).update(TAG_ID_RX.findall(title))
    for rel, n, kind, title in titles:
        for sid in TAG_ID_RX.findall(title):
            if sid not in stories:
                out.append(Finding(rel, n, "orphan-tag", f"@{sid} names no story"))
        for sid, number in TAG_AC_RX.findall(title):
            story = stories.get(sid)
            if not story or int(number) not in story.criteria:
                out.append(Finding(rel, n, "orphan-tag", f"@{sid}-ac{number} names no criterion",
                                   sid if story else ""))
                continue
            if kind != "test":
                continue
            covered.add((sid, int(number)))
            if sid not in set(TAG_ID_RX.findall(title)) | carried.get(rel, set()):
                out.append(Finding(rel, n, "test-tag", f"covers @{sid}-ac{number} but does not carry @{sid}", sid))
    for story in stories.values():
        if story.status != "ready":
            continue
        for number, (line, _, _) in sorted(story.criteria.items()):
            if (story.id, number) not in covered:
                out.append(Finding(story.path, line, "coverage",
                                   f"AC{number} has no test tagged @{story.id}-ac{number}", story.id))
    return out


def load_settings(root: Path) -> tuple[dict, list[Finding]]:
    rel = f"{SPEC}/spec.toml"
    path = root / rel
    if not path.exists():
        return {}, [Finding(rel, 1, "schema", "missing (name, version, locales)")]
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return {}, [Finding(rel, 1, "schema", str(exc))]
    out = [Finding(rel, 1, "schema", f"unknown key '{k}'") for k in data
           if k not in ("name", "version", "locales", "neutrality")]
    if not isinstance(data.get("name"), str) or not data["name"]:
        out.append(Finding(rel, 1, "schema", "name is required"))
    if not SEMVER_RX.match(str(data.get("version", ""))):
        out.append(Finding(rel, 1, "schema", "version reads X.Y.Z"))
    locales = data.get("locales")
    if not isinstance(locales, list) or not locales or not all(isinstance(x, str) for x in locales):
        out.append(Finding(rel, 1, "schema", "locales is a non-empty list of locales, e.g. [\"fr\"]"))
        locales = []
    for locale in locales:
        copy = f"{SPEC}/ui/copy.{locale}.json"
        try:
            if not isinstance(json.loads((root / copy).read_text(encoding="utf-8")), dict):
                out.append(Finding(copy, 1, "schema", "a label catalogue is a JSON object"))
        except OSError:
            out.append(Finding(copy, 1, "schema", f"missing label catalogue of locale '{locale}'"))
        except json.JSONDecodeError as exc:
            out.append(Finding(copy, exc.lineno, "schema", f"invalid JSON: {exc.msg}"))
    neutral = data.get("neutrality", {})
    clean = {}
    for key, value in (neutral.items() if isinstance(neutral, dict) else [("neutrality", None)]):
        if key not in ("extra", "allow"):
            out.append(Finding(rel, 1, "schema", f"unknown key 'neutrality.{key}'"))
        elif not isinstance(value, list) or not all(isinstance(w, str) for w in value):
            out.append(Finding(rel, 1, "schema", f"neutrality.{key} is a list of words"))
        else:
            clean[key] = value
    data["neutrality"] = clean
    return data, out


def _lifted(finding: Finding, stories: dict) -> bool:
    story = stories.get(finding.story)
    if not story or finding.rule not in story.exempt:
        return False
    return not (finding.rule == "schema" and story.status == "ready")


def lint(root: Path) -> list[Finding]:
    if not (root / SPEC).is_dir():
        fail(EXIT_PRECONDITION, f"no {SPEC}/ folder in {root}")
    settings, found = load_settings(root)
    terms = lexicon(settings)
    stories: dict[str, Story] = {}
    for path in sorted((root / STORIES).glob("*.md")):
        rel = path.relative_to(root).as_posix()
        story, problems = parse_story(rel, path.read_text(encoding="utf-8"))
        found += problems + _neutrality(story, terms) + _extensions(story)
        if story.status == "ready":
            found += _ready_schema(story)
        if story.id in stories:
            found.append(Finding(rel, 1, "schema", f"id {story.id} is also used by {stories[story.id].path}", story.id))
        elif story.id:
            stories[story.id] = story
    found += _tests(scan_titles(root), stories)
    kept = [f for f in found if not _lifted(f, stories)]
    return sorted(kept, key=lambda f: (f.path, f.line, f.rule, f.message))


def _report(findings: list[Finding]) -> int:
    for finding in findings:
        print(finding)
    print("spec: " + ("red" if findings else "green"))
    return EXIT_RED if findings else EXIT_OK


# -- versions --------------------------------------------------------------------------------

def semver(text: str) -> tuple[int, int, int]:
    match = SEMVER_RX.match(text or "")
    if not match:
        fail(EXIT_ERROR, f"invalid version '{text}' (expected X.Y.Z)")
    return tuple(int(x) for x in match.groups())


def clean_version(text: str) -> str:
    value = (text or "").strip()
    for prefix in ("spec-v", "v"):
        if value.startswith(prefix):
            value = value[len(prefix):]
            break
    semver(value)
    return value


def criteria_at(git: Git, rev: str) -> dict[str, str]:
    """Criteria of the ready stories at a revision: '<id>-ac<n>' -> '@<label> — <text>'."""
    proc = git.run("ls-tree", "--name-only", f"{rev}:{STORIES}", check=False)
    out = {}
    for name in proc.stdout.splitlines() if proc.returncode == 0 else []:
        if not FILE_RX.match(name):
            continue
        story, _ = parse_story(f"{STORIES}/{name}", git.show(rev, f"{STORIES}/{name}") or "")
        if story.status == "ready":
            for n, (_, label, text) in story.criteria.items():
                out[f"{story.id}-ac{n}"] = f"@{label} — {text}"
    return out


def diff_criteria(before: dict, after: dict) -> dict[str, list]:
    return {"removed": [(k, before[k]) for k in sorted(before) if k not in after],
            "changed": [(k, after[k]) for k in sorted(after) if k in before and before[k] != after[k]],
            "added": [(k, after[k]) for k in sorted(after) if k not in before]}


def level_of(changes: dict) -> str:
    if changes["removed"] or changes["changed"]:
        return "major"
    return "minor" if changes["added"] else "patch"


def next_version(previous: str | None, level: str, stage: str) -> str:
    """First release: 0.1.0. Before the first delivery, a 0.x stays 0.x: major -> minor, others ->
    patch."""
    if not previous:
        return "0.1.0"
    major, minor, patch = semver(previous)
    if stage == "pre-release" and major == 0:
        level = "minor" if level == "major" else "patch"
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def bump_level(previous: str, version: str) -> str | None:
    """Level of the step from previous to version; None when version is not above previous."""
    a, b = semver(previous), semver(version)
    if b <= a:
        return None
    return "major" if b[0] != a[0] else "minor" if b[1] != a[1] else "patch"


def previous_version(git: Git) -> str | None:
    found = [semver(t[len("spec-v"):]) for t in git.out("tag", "--list", "spec-v*").splitlines()
             if SEMVER_RX.match(t[len("spec-v"):])]
    return ".".join(str(x) for x in max(found)) if found else None


def changelog_entry(version: str, level: str, changes: dict) -> str:
    lines = [f"## {version}", "", f"Level: {level}"]
    for key, title in (("removed", "Removed"), ("changed", "Changed"), ("added", "Added")):
        if changes[key]:
            lines += ["", f"### {title}"] + [f"- {cid} {text}" for cid, text in changes[key]]
    if not any(changes.values()):
        lines += ["", "No acceptance criterion changed."]
    return "\n".join(lines) + "\n"


def write_changelog(root: Path, version: str, entry: str) -> bool:
    """Insert the entry above the latest version (newest first); False when already there."""
    path = root / SPEC / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8") if path.exists() else "# Changelog\n"
    if re.search(rf"^## {re.escape(version)}\s*$", text, re.MULTILINE):
        return False
    lines = text.splitlines(keepends=True)
    cut = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    head, tail = "".join(lines[:cut]).rstrip("\n") + "\n\n", "".join(lines[cut:])
    path.write_text(head + entry + ("\n" + tail if tail else ""), encoding="utf-8")
    return True


def write_version(root: Path, version: str) -> bool:
    path = root / SPEC / "spec.toml"
    if not path.exists():
        return False
    text, count = re.subn(r'(?m)^version\s*=\s*"[^"]*"', f'version = "{version}"',
                          path.read_text(encoding="utf-8"), count=1)
    if count:
        path.write_text(text, encoding="utf-8")
    return bool(count)


def _check_requested(git: Git, requested: str, previous: str | None, level: str, stage: str) -> str:
    version = clean_version(requested)
    given = bump_level(previous, version) if previous else None
    if previous and given is None:
        fail(EXIT_ERROR, f"{version} is not above the previous version {previous}")
    if stage == "pre-release" and semver(version)[0] >= 1 and (not previous or semver(previous)[0] == 0):
        fail(EXIT_PRECONDITION, "release_stage is pre-release: versions stay 0.x until the first "
                                "delivery to a third party")
    if stage == "released" and given and LEVELS.index(given) < LEVELS.index(level):
        override = " ".join(trailer_values(git.out("log", "-1", "--format=%B", "HEAD", check=False),
                                           "Version-Override"))
        if not override:
            fail(EXIT_RED, f"{version} is a {given} release but the criteria call for a {level} one; "
                           "to keep it, commit with the trailer 'Version-Override: <reason>' and run again")
        print(f"override: {override}")
    return version


def release(root: Path, requested: str | None = None) -> int:
    require_human("deliveryctl spec release")
    require_local("deliveryctl spec release")
    cfg = config.load(root)
    if cfg.repo_role == "impl":
        fail(EXIT_PRECONDITION, "spec release runs where the spec is written: here spec/ is a synced copy")
    findings = lint(root)
    if findings:
        return _report(findings)
    git = Git(root)
    if git.out("status", "--porcelain", "--", SPEC, f":!{SPEC}/CHANGELOG.md", f":!{SPEC}/spec.toml"):
        fail(EXIT_PRECONDITION, "commit spec/ first: the release compares HEAD with the previous tag")
    previous = previous_version(git)
    if previous and git.blob("HEAD", SPEC) == git.blob(f"spec-v{previous}", SPEC):
        fail(EXIT_PRECONDITION, f"spec/ has not changed since spec-v{previous}")
    changes = diff_criteria(criteria_at(git, f"spec-v{previous}") if previous else {}, criteria_at(git, "HEAD"))
    level = level_of(changes)
    version = next_version(previous, level, cfg.release_stage)
    if requested:
        version = _check_requested(git, requested, previous, level, cfg.release_stage)
    tag = f"spec-v{version}"
    if git.ok("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"):
        fail(EXIT_PRECONDITION, f"tag {tag} already exists")
    wrote = write_changelog(root, version, changelog_entry(version, level, changes))
    write_version(root, version)
    counts = ", ".join(f"{len(changes[k])} {k}" for k in ("added", "changed", "removed"))
    print("spec: green")
    print(f"previous: {'spec-v' + previous if previous else 'none'}")
    print(f"criteria: {counts} -> {level}")
    print(f"version: {version} ({cfg.release_stage})")
    print(f"draft: {SPEC}/CHANGELOG.md" + ("" if wrote else " (entry already there)") +
          f", {SPEC}/spec.toml — review them, then run:")
    print(f"  git add {SPEC}/CHANGELOG.md {SPEC}/spec.toml")
    print(f'  git commit -m "Release spec {version}"')
    print(f'  git tag -a {tag} -m "spec {version}"')
    print(f"  git push origin {git.branch()} {tag}")
    return EXIT_OK


# -- copy in an implementation repository ----------------------------------------------------

def read_lock(text: str | None) -> dict:
    if text is None:
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        fail(EXIT_RED, f"{LOCK}: {exc}")


def merged_refs(git: Git) -> dict[str, tuple[str, str]]:
    """Latest 'Spec:' merge trailer per spec story on HEAD: id -> (reference, blob prefix)."""
    out = {}
    for message in git.out("log", "--format=%B%x00", "HEAD", check=False).split("\x00"):
        for m in SPEC_TRAILER_RX.finditer(message):
            if m.group(1) not in out:
                out[m.group(1)] = (m.group(0).split(":", 1)[1].strip(), m.group(3) or "")
    return out


def conformance(git: Git, rev: str, version: str, source: str) -> tuple[str, list[str]]:
    """docs/conformance.md for the spec at rev, and the status of each story."""
    merged, rows, statuses = merged_refs(git), [], []
    for entry in git.run("ls-tree", f"{rev}:{STORIES}", check=False).stdout.splitlines():
        meta, _, name = entry.partition("\t")
        match = FILE_RX.match(name)
        if not match or meta.split()[1:2] != ["blob"]:
            continue
        sid, blob = match.group(1), meta.split()[2]
        try:
            title = str(fm.split(git.show(rev, f"{STORIES}/{name}") or "")[0].get("title") or "")
        except fm.FrontmatterError:
            title = ""
        last = merged.get(sid)
        status = "not merged" if not last else "conforming" if last[1] and blob.startswith(last[1]) else "outdated"
        statuses.append(status)
        rows.append(f"| {sid} | {title.replace('|', '/')} | {sid}@{version}#{blob[:7]} | {status} | "
                    f"{last[0] if last else '—'} |")
    text = "\n".join([
        "# Conformance", "",
        f"Spec {version}, {source} at {rev[:12]}. Written by `deliveryctl spec sync`: a story "
        "conforms when the blob named by its last merge trailer 'Spec:' is its current blob.", "",
        "| Story | Title | Reference | Status | Last merge |", "|---|---|---|---|---|", *rows, ""])
    return text, statuses


def sync(root: Path, version: str | None, source: str | None) -> int:
    require_human("deliveryctl spec sync")
    cfg = config.load(root)
    if cfg.repo_role != "impl":
        fail(EXIT_PRECONDITION, 'spec sync runs in an implementation repository (repo_role = "impl")')
    if not version:
        fail(EXIT_ERROR, "usage: deliveryctl spec sync <version> [--source URL]")
    version = clean_version(version)
    lock_path = root / LOCK
    source = source or read_lock(lock_path.read_text(encoding="utf-8") if lock_path.exists() else None).get("source")
    if not source:
        fail(EXIT_ERROR, "no source: pass --source <spec repository> (it is then kept in spec.lock)")
    if Path(source).exists():
        source = str(Path(source).resolve())
    git = Git(root)
    if git.out("status", "--porcelain", "--untracked-files=no") or git.out("status", "--porcelain", "--", SPEC):
        fail(EXIT_PRECONDITION, "commit or stash local changes first: the sync is a single commit")
    tag = f"spec-v{version}"
    git.run("fetch", "--no-tags", source, f"refs/tags/{tag}", timeout=180)
    if not git.ok("rev-parse", "--verify", "--quiet", "FETCH_HEAD:spec"):
        fail(EXIT_PRECONDITION, f"{tag} of {source} has no spec/ folder")
    commit = git.out("rev-parse", "FETCH_HEAD^{commit}")
    tree = git.out("rev-parse", "FETCH_HEAD:spec")
    git.run("rm", "-r", "-q", "--ignore-unmatch", SPEC)
    git.run("read-tree", f"--prefix={SPEC}/", "-u", "FETCH_HEAD:spec")
    lock_path.write_text("# Written by 'deliveryctl spec sync'; never edited by hand.\n" + "".join(
        f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
        for key, value in (("source", source), ("version", version), ("commit", commit), ("tree", tree))),
        encoding="utf-8")
    report = root / CONFORMANCE
    report.parent.mkdir(parents=True, exist_ok=True)
    text, statuses = conformance(git, commit, version, source)
    report.write_text(text, encoding="utf-8")
    git.run("add", "--", SPEC, LOCK, CONFORMANCE)
    if git.ok("diff", "--cached", "--quiet"):
        print(f"spec: already at {version} ({commit[:12]}); nothing to commit")
        return EXIT_OK
    sha = git.commit([], f"Sync spec {version}", trailers=[
        ("Spec-Version", version), ("Spec-Commit", commit), ("Delivery-Method", VERSION)])
    print(f"synced spec {version} ({commit[:12]}) in {sha[:12]}: {len(statuses)} stories, "
          f"{statuses.count('conforming')} conforming, {statuses.count('outdated')} outdated "
          f"(see {CONFORMANCE}); push is yours")
    return EXIT_OK


def verify(root: Path) -> int:
    git = Git(root)
    lock = read_lock(git.show("HEAD", LOCK))
    if not lock:
        fail(EXIT_PRECONDITION, f"no {LOCK} at HEAD: run 'deliveryctl spec sync <version>' first")
    have = git.blob("HEAD", SPEC) or "missing"
    if have == lock.get("tree"):
        print(f"HEAD:spec is spec-v{lock.get('version')} (tree {have[:12]})")
        print("spec: green")
        return EXIT_OK
    print(f"HEAD:spec is {have[:12]}, {LOCK} expects {str(lock.get('tree'))[:12]} (spec-v{lock.get('version')}): "
          "spec/ is changed only by 'deliveryctl spec sync'")
    print("spec: red")
    return EXIT_RED


def main(args) -> int:
    root = repo_root()
    if args.action == "lint":
        return _report(lint(root))
    if args.action == "release":
        return release(root, args.version)
    if args.action == "sync":
        return sync(root, args.version, args.source)
    return verify(root)
