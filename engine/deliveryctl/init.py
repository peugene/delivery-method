"""`deliveryctl init [--role R] [--upgrade] [--dry-run]`: equip the current repository with the
method, or refresh its engine copy (CONTRACTS.md §2, §12.2). Every change is planned before
any is written, so a conflict leaves the repository untouched. Never overwrites, never commits;
`--upgrade` refreshes the engine copy, the rules, the templates and the marketplace ref only."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import config, roles
from .core import EXIT_ERROR, EXIT_OK, EXIT_PRECONDITION, fail, main_root, repo_root, run

PLUGIN_KEY = "delivery-method@delivery-method"
MARKETPLACE = "delivery-method"
DEFAULT_REPO = "peugene/delivery-method"
RULES_IMPORT = "@.delivery/rules.md"
CONVENTIONS_RX = re.compile(r"^##\s+Project conventions\s*$", re.MULTILINE)
GITIGNORE = (".delivery/run/", ".delivery/**/__pycache__/", "docs/stories/*/work/",
             "docs/campaigns/work/", "qualification/work/", "test-results/", "playwright-report/",
             "spec/acceptance/node_modules/")
# Human gestures (§12.1) asked for in Claude sessions. 'story close' is left out: the engine
# refuses it for a stopped story in a role session, and the lead closes merged stories.
GESTURES = ("init", "run", "merge", "spec release", "spec sync", "nightly", "note",
            "journal report", "qualify submit")
LANGUAGE_RX = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc")
LAUNCHER = '''#!/usr/bin/env python3
"""Engine of the delivery method for this project. Written by 'deliveryctl init', refreshed by
'deliveryctl init --upgrade'; never edited by hand."""
import sys
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("deliveryctl needs Python 3.11 or later")
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "engine"))
from deliveryctl.cli import main  # noqa: E402

sys.exit(main())
'''


@dataclass
class Step:
    path: str
    status: str                                  # created | kept | merged | updated
    write: Callable[[], None] | None = None


# -- plugin source --------------------------------------------------------------------------
def is_plugin(path: Path | None) -> bool:
    return bool(path) and all((Path(path) / rel).exists() for rel in (
        ".claude-plugin/plugin.json", "engine/deliveryctl/cli.py", "rules/rules.md", "templates"))


def plugin_source() -> Path:
    """The plugin this engine belongs to, else the one the machine knows (a project copy
    upgrading itself)."""
    here = Path(__file__).resolve().parents[2]
    if is_plugin(here):
        return here
    found = roles.plugin_root()
    if is_plugin(found):
        return found
    fail(EXIT_PRECONDITION, "plugin not found: run the plugin's deliveryctl, or set plugin_dir "
                            "in ~/.config/delivery-method/machine.toml")


def engine_version(plugin: Path) -> str:
    text = (Path(plugin) / "engine" / "deliveryctl" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        fail(EXIT_ERROR, f"{plugin}: engine version not found")
    return match.group(1)


def version_key(version: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def copy_version(root: Path) -> str:
    path = Path(root) / ".delivery" / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def plugin_repo(plugin: Path) -> str:
    try:
        data = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_REPO
    match = re.search(r"github\.com[/:]([\w.-]+/[\w.-]+?)(?:\.git)?/?$", str(data.get("repository", "")))
    return match.group(1) if match else DEFAULT_REPO


def digest(folder: Path) -> dict:
    """Content of a folder by relative path, without bytecode."""
    return {p.relative_to(folder).as_posix(): hashlib.sha1(p.read_bytes()).hexdigest()
            for p in sorted(Path(folder).rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


# -- steps ----------------------------------------------------------------------------------
def _writer(path: Path, text: str, executable: bool = False) -> Callable[[], None]:
    def write():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if executable:
            path.chmod(0o755)
    return write


def file_step(root: Path, rel: str, text: str, refresh: bool = False, executable: bool = False) -> Step:
    dest = root / rel
    if not dest.exists():
        return Step(rel, "created", _writer(dest, text, executable))
    same = dest.read_text(encoding="utf-8", errors="replace") == text
    if executable:
        same = same and bool(dest.stat().st_mode & 0o100)
    if same or not refresh:
        return Step(rel, "kept")
    return Step(rel, "updated", _writer(dest, text, executable))


def dir_step(root: Path, rel: str, source: Path, refresh: bool = False) -> Step:
    dest = root / rel

    def write():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest, ignore=IGNORED)
    if not dest.exists():
        return Step(rel + "/", "created", write)
    if not refresh or digest(dest) == digest(source):
        return Step(rel + "/", "kept")
    return Step(rel + "/", "updated", write)


def engine_steps(root: Path, plugin: Path, version: str, refresh: bool) -> list[Step]:
    rules = (plugin / "rules" / "rules.md").read_text(encoding="utf-8")
    return [dir_step(root, ".delivery/engine/deliveryctl", plugin / "engine" / "deliveryctl", refresh),
            dir_step(root, ".delivery/templates", plugin / "templates", refresh),
            file_step(root, ".delivery/rules.md", rules, refresh),
            file_step(root, ".delivery/VERSION", version + "\n", refresh),
            file_step(root, ".delivery/deliveryctl", LAUNCHER, refresh, executable=True)]


def _set_toml(text: str, key: str, value) -> str:
    rx = re.compile(rf'^({re.escape(key)}\s*=\s*)("(?:[^"\\]|\\.)*"|\[[^\]]*\]|[^\s#]+)', re.MULTILINE)
    literal = json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value)
    text, count = rx.subn(lambda m: m.group(1) + literal, text, count=1)
    if not count:
        fail(EXIT_ERROR, f"templates/project/delivery.toml has no '{key}' line")
    return text


def detect_forge(root: Path) -> str:
    proc = run(["git", "remote", "get-url", "origin"], cwd=root, check=False)
    url = proc.stdout.strip().lower()
    if proc.returncode != 0 or not url:
        return "none"
    for kind in ("github", "gitlab"):
        if kind in url:
            return kind
    fail(EXIT_PRECONDITION, "cannot tell the forge from the origin URL: pass --forge github|gitlab|none")


def agent_prefix(name: str) -> str:
    words = [w for w in re.split(r"[^a-z0-9]+", name.lower()) if w]
    prefix = words[0][:4] if len(words) == 1 else "".join(w[0] for w in words)[:4]
    return prefix or "dm"


def project_toml(root: Path, plugin: Path, args, forge: str) -> str:
    language = args.language or "fr"
    if not LANGUAGE_RX.match(language):
        fail(EXIT_ERROR, f"--language takes a language code such as fr or en, got '{language}'")
    text = (plugin / "templates" / "project" / "delivery.toml").read_text(encoding="utf-8")
    values = {"repo_role": args.role, "content_language": language, "forge": forge,
              "agent_prefix": agent_prefix(root.name), "check": args.check or "just check",
              "acceptance": args.acceptance or "just acceptance {grep}", "serve": args.serve or "just serve {port}"}
    for key, value in values.items():
        text = _set_toml(text, key, value)
    config.parse(tomllib.loads(text), root, "delivery.toml (answers of init)")
    return text


def claude_md_step(root: Path, plugin: Path) -> Step:
    path = root / "CLAUDE.md"
    if not path.exists():
        template = (plugin / "templates" / "project" / "CLAUDE.md").read_text(encoding="utf-8")
        return Step("CLAUDE.md", "created", _writer(path, template))
    text = path.read_text(encoding="utf-8")
    additions = []
    if not any(line.strip() == RULES_IMPORT for line in text.splitlines()):
        additions.append(RULES_IMPORT)
    if not CONVENTIONS_RX.search(text):
        additions.append("## Project conventions")
    if not additions:
        return Step("CLAUDE.md", "kept")
    new = text + ("\n" if text and not text.endswith("\n") else "") + "\n" + "\n\n".join(additions) + "\n"
    return Step("CLAUDE.md", "merged", _writer(path, new))


def ask_rules() -> list[str]:
    rules = []
    for launcher in ("deliveryctl", ".delivery/deliveryctl"):
        for verb in GESTURES:
            rules += [f"Bash({launcher} {verb})", f"Bash({launcher} {verb} *)"]
        rules.append(f"Bash({launcher} story next *--go*)")
    return rules


def wanted_settings(plugin: Path, version: str) -> dict:
    source = {"source": "github", "repo": plugin_repo(plugin), "ref": f"{MARKETPLACE}--v{version}"}
    return {"enabledPlugins": {PLUGIN_KEY: True},
            "extraKnownMarketplaces": {MARKETPLACE: {"source": source}},
            "permissions": {"deny": ["SendMessage"], "ask": ask_rules()}}


def add_only(current: dict, wanted: dict, where: str = "") -> list[str]:
    """Merge `wanted` into `current` by addition; returns the values that diverge."""
    conflicts = []
    for key, value in wanted.items():
        path = f"{where}.{key}" if where else key
        if key not in current:
            current[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(current[key], dict):
            conflicts += add_only(current[key], value, path)
        elif isinstance(value, list) and isinstance(current[key], list):
            current[key] += [item for item in value if item not in current[key]]
        elif current[key] != value:
            conflicts.append(f"{path}: {json.dumps(current[key])} (the method needs {json.dumps(value)})")
    return conflicts


def merge_settings(current: dict, wanted: dict, refresh: bool) -> tuple[dict, list[str]]:
    """Once declared, the marketplace source belongs to the team (a fork, an internal mirror):
    init only adds its ref, and --upgrade refreshes it."""
    merged = copy.deepcopy(current)
    ref = wanted["extraKnownMarketplaces"][MARKETPLACE]["source"]["ref"]
    known = merged.get("extraKnownMarketplaces")
    entry = known.get(MARKETPLACE) if isinstance(known, dict) else None
    if isinstance(entry, dict):
        wanted = {k: v for k, v in wanted.items() if k != "extraKnownMarketplaces"}
        source = entry.get("source")
        pinned = isinstance(source, dict) and ("ref" in source or source.get("source") in ("github", "git"))
        if pinned and (refresh or "ref" not in source):
            source["ref"] = ref
    if refresh:
        return merged, []
    return merged, add_only(merged, wanted)


def settings_step(root: Path, plugin: Path, version: str, refresh: bool) -> Step | None:
    path = root / ".claude" / "settings.json"
    wanted = wanted_settings(plugin, version)
    if not path.exists():
        return None if refresh else Step(".claude/settings.json", "created",
                                         _writer(path, json.dumps(wanted, indent=2) + "\n"))
    try:
        current = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(EXIT_ERROR, f".claude/settings.json is not valid JSON: {exc}")
    if not isinstance(current, dict):
        fail(EXIT_ERROR, ".claude/settings.json must hold a JSON object")
    merged, conflicts = merge_settings(current, wanted, refresh)
    if conflicts:
        fail(EXIT_PRECONDITION, ".claude/settings.json holds values that diverge from what the method "
                                "needs; fix them by hand, then run init again:\n  " + "\n  ".join(conflicts))
    if merged == current:
        return Step(".claude/settings.json", "kept")
    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    return Step(".claude/settings.json", "updated" if refresh else "merged", _writer(path, text))


def missing_gitignore(text: str) -> list[str]:
    present = {line.strip().strip("/") for line in text.splitlines()}
    return [line for line in GITIGNORE if line.strip("/") not in present]


def gitignore_step(root: Path) -> Step:
    path = root / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    missing = missing_gitignore(text)
    if not missing:
        return Step(".gitignore", "kept")
    new = text + ("\n" if text and not text.endswith("\n") else "") + "\n".join(missing) + "\n"
    return Step(".gitignore", "merged" if path.exists() else "created", _writer(path, new))


def template_step(root: Path, plugin: Path, rel: str, template: str) -> Step:
    """A starter file written only when absent."""
    text = (plugin / "templates" / "project" / template).read_text(encoding="utf-8")
    return file_step(root, rel, text)


SPEC_SKELETON = ("spec.toml", "harness-contract.md", "ui/copy.fr.json", "acceptance/copy.ts",
                 "acceptance/package.json", "acceptance/playwright.config.ts",
                 "acceptance/fixtures/empty-app/server.mjs")


def spec_steps(root: Path, plugin: Path) -> list[Step]:
    """A spec/ skeleton for a repository that writes the specification (created only when spec/
    is absent; the example test is left out so that spec lint starts green)."""
    if (root / "spec").exists():
        return [Step("spec/", "kept")]
    source = plugin / "templates" / "spec"
    steps = []
    for rel in SPEC_SKELETON:
        dest = "spec/" + (rel if rel != "harness-contract.md" else "acceptance/harness-contract.md")
        steps.append(file_step(root, dest, (source / rel).read_text(encoding="utf-8")))
    steps.append(file_step(root, "spec/CHANGELOG.md", "# Changelog de la spécification\n"))
    steps.append(file_step(root, "spec/product/brief.md", "# Brief\n"))
    steps.append(file_step(root, "spec/product/glossary.md", "# Glossaire\n"))
    return steps


def install_steps(root: Path, plugin: Path, version: str, args, notes: list[str]) -> tuple[list[Step], str]:
    toml_path = root / config.PROJECT_FILE
    answers = [f"--{k}" for k in ("role", "language", "forge", "check", "acceptance", "serve")
               if getattr(args, k, None)]
    if toml_path.exists():
        forge = config.load(root).forge
        if answers:
            notes.append(f"delivery.toml exists: {', '.join(answers)} ignored (edit the file)")
        steps = [Step("delivery.toml", "kept")]
    else:
        if not args.role:
            fail(EXIT_PRECONDITION, "delivery.toml not found: say what this repository holds "
                                    "with --role single|spec|impl")
        forge = args.forge or detect_forge(root)
        if not args.forge:
            notes.append(f"forge = {forge}, read from the origin remote (--forge to choose)")
        steps = [Step("delivery.toml", "created", _writer(toml_path, project_toml(root, plugin, args, forge)))]
    existing = copy_version(root)
    if existing and existing != version:
        notes.append(f"engine copy {existing}, plugin {version}: 'deliveryctl init --upgrade' refreshes it")
    steps += engine_steps(root, plugin, version, refresh=False)
    steps.append(claude_md_step(root, plugin))
    steps.append(settings_step(root, plugin, existing or version, refresh=False))
    steps.append(gitignore_step(root))
    justfile = next((p.name for p in root.iterdir() if p.name.lower() in ("justfile", ".justfile")), "")
    steps.append(Step(justfile, "kept") if justfile else template_step(root, plugin, "justfile", "justfile"))
    repo_role = config.load(root).repo_role if toml_path.exists() else args.role
    if repo_role in ("spec", "single"):
        steps += spec_steps(root, plugin)
    if forge == "github":
        steps.append(template_step(root, plugin, ".github/workflows/delivery.yml", "github-ci.yml"))
    elif forge == "gitlab":
        steps.append(template_step(root, plugin, ".gitlab/delivery-ci.yml", "gitlab-ci.yml"))
    return steps, forge


def next_steps(root: Path, steps: list[Step], forge: str, upgrade: bool) -> list[str]:
    changed = [s.path for s in steps if s.status != "kept"]
    if not changed:
        return ["Rien à changer : le dépôt est déjà équipé. Diagnostic : .delivery/deliveryctl doctor"]
    paths = sorted({".delivery" if p.startswith(".delivery/") else p.rstrip("/") for p in changed})
    lines = ["Relisez le diff de .delivery/ et de .claude/settings.json, puis commitez-le."] if upgrade else \
        ["Relisez les fichiers posés, puis commitez-les (init ne commite rien) :"]
    lines.append("  git add " + " ".join(paths))
    mode = run(["git", "config", "--get", "core.fileMode"], cwd=root, check=False).stdout.strip()
    if mode == "false" and ".delivery" in paths:
        lines.append("  git update-index --chmod=+x .delivery/deliveryctl   (ce système de fichiers "
                     "ne garde pas le bit exécutable)")
    if "justfile" in changed:
        lines.append("Remplacez les recettes d'amorce du justfile (check, acceptance, serve) par celles "
                     "de votre pile : elles échouent tant qu'elles ne sont pas définies.")
    gitlab_ci = root / ".gitlab-ci.yml"
    if forge == "gitlab" and ".gitlab/delivery-ci.yml" not in (
            gitlab_ci.read_text(encoding="utf-8") if gitlab_ci.exists() else ""):
        lines += ["Ajoutez à .gitlab-ci.yml :", "  include:", "    - local: .gitlab/delivery-ci.yml"]
    if not config.machine_path().exists():
        lines.append(f"Réglages de la machine (notifications, journal) : {config.machine_path()} "
                     "(CONTRACTS.md §4).")
    lines.append("Diagnostic : .delivery/deliveryctl doctor")
    return lines


def main(args) -> int:
    root = repo_root()
    if root.resolve() != main_root().resolve():
        fail(EXIT_PRECONDITION, "run init in the main checkout, not in a story worktree")
    plugin = plugin_source()
    version = engine_version(plugin)
    notes: list[str] = []
    if args.upgrade:
        if not (root / config.PROJECT_FILE).exists():
            fail(EXIT_PRECONDITION, "delivery.toml not found: run 'deliveryctl init --role R' first")
        existing = copy_version(root)
        if existing and version_key(existing) > version_key(version):
            fail(EXIT_PRECONDITION, f"the project engine {existing} is newer than the plugin {version}: "
                                    "update the plugin first")
        steps = engine_steps(root, plugin, version, refresh=True)
        steps.append(settings_step(root, plugin, version, refresh=True))
        forge = ""
    else:
        steps, forge = install_steps(root, plugin, version, args, notes)
    steps = [s for s in steps if s]
    if not args.dry_run:
        for step in steps:
            if step.write:
                step.write()
    print(f"deliveryctl init{' --upgrade' if args.upgrade else ''}: {root} (plugin {version})"
          + (" — dry run, nothing written" if args.dry_run else ""))
    for step in steps:
        print(f"  {step.status:8} {step.path}")
    for note in notes:
        print(f"note: {note}")
    if args.dry_run:
        print("\nRelancez sans --dry-run pour appliquer.")
        return EXIT_OK
    print("\nProchaines étapes :")
    for line in next_steps(root, steps, forge, args.upgrade):
        print("  " + line)
    return EXIT_OK
