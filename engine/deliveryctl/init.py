"""`deliveryctl init [single|spec|impl [SPEC]] [NAME] [--upgrade] [--dry-run] [--yes]`: equip a
repository with the method, or refresh its copy of it (CONTRACTS.md §2, §12.2). Every change is
planned before any is written, so a conflict leaves the repository untouched. After one summary and
one "ok", it does the forge gestures too: creates the repository when there is none, sets the git
address of a public one, commits what it laid down, pushes it, and protects the default branch.
`--upgrade` refreshes what the method owns: the engine copy, the rules, the templates, the copy
of the agents, skills and commands (recorded in `.delivery/method.json`), the method's settings,
the marketplace ref and the missing `.gitignore` lines."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import config, create, roles
from .core import (EXIT_ERROR, EXIT_OK, EXIT_PRECONDITION, EXIT_TOOL, DeliveryError, fail, main_root, repo_root,
                   run)
from .forge import Forge
from .gitops import Git

PLUGIN_KEY = "delivery-method@delivery-method"
PLUGIN_NAMESPACE = "delivery-method"
MARKETPLACE = "delivery-method"
DEFAULT_REPO = "peugene/delivery-method"
RULES_IMPORT = "@.delivery/rules.md"
CONVENTIONS_RX = re.compile(r"^##\s+Project conventions\s*$", re.MULTILINE)
GITIGNORE = (".delivery/run/", ".delivery/**/__pycache__/", "docs/stories/*/work/",
             "docs/campaigns/work/", "qualification/work/", "test-results/", "playwright-report/",
             "spec/acceptance/node_modules/", "docs/maybe/*.draft.md")
# Human gestures (§12.1) asked for in Claude sessions. 'story close' is left out: the engine
# refuses it for a stopped story in a role session, and the lead closes merged stories.
GESTURES = ("init", "run", "merge", "spec release", "spec sync", "nightly", "note",
            "journal report", "qualify submit")
MANIFEST = ".delivery/method.json"
COPY_SOURCES = ("agents", "skills", "commands")
NOT_COPIED = {"commands/init.md"}               # init stays a plugin command: it equips a project
HOOK_STOP = '"$CLAUDE_PROJECT_DIR"/.delivery/deliveryctl hook stop'
HOOK_SESSION_START = '"$CLAUDE_PROJECT_DIR"/.delivery/deliveryctl hook session-start'
HOOK_PRE_TOOL = '"$CLAUDE_PROJECT_DIR"/.delivery/deliveryctl hook pre-tool'
PRE_TOOL_FILTERS = ("Bash(deliveryctl *)", "Bash(.delivery/deliveryctl *)")
HOOK_MARK = "deliveryctl hook "
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


# -- the method's agents, skills and commands, copied into .claude/ ---------------------------
def method_files(plugin: Path) -> dict[str, bytes]:
    """What the project copy holds, by project path: the plugin's agents, skills and commands, with
    the plugin namespace removed from references to those same components."""
    sources = {}
    for kind in COPY_SOURCES:
        folder = plugin / kind
        for path in sorted(folder.rglob("*")):
            rel = path.relative_to(plugin).as_posix()
            if path.is_file() and rel not in NOT_COPIED and "__pycache__" not in path.parts:
                sources[rel] = path
    names = {name for rel in sources for name in (_component(rel),) if name}
    alternatives = "|".join(sorted(map(re.escape, names), key=len, reverse=True))
    rx = re.compile(rf"(?<![\w-])(/?){re.escape(PLUGIN_NAMESPACE)}:({alternatives})(?![\w-])")
    files = {}
    for rel, path in sources.items():
        data = path.read_bytes()
        if path.suffix == ".md":
            data = rx.sub(r"\1\2", data.decode("utf-8")).encode("utf-8")
        files[".claude/" + rel] = data
    return files


def _component(rel: str) -> str:
    """Name of the agent, skill or command a plugin file belongs to."""
    parts = rel.split("/")
    if parts[0] == "skills":
        return parts[1] if len(parts) > 2 else ""
    return Path(parts[-1]).stem if len(parts) == 2 else ""


def sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def read_manifest(root: Path) -> dict:
    """The version and the digest of each copied file, as written; empty when absent."""
    try:
        data = json.loads((Path(root) / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) and isinstance(data.get("files"), dict) else {}


def _unlinker(root: Path, rel: str) -> Callable[[], None]:
    def write():
        path = root / rel
        path.unlink()
        for parent in path.parents:
            if parent in (root / ".claude", root) or any(parent.iterdir()):
                break
            parent.rmdir()
    return write


def method_steps(root: Path, plugin: Path, version: str, refresh: bool) -> list[Step]:
    """The copy and its manifest. A file at a copy path that the manifest does not vouch for,
    or that was edited since, is the project's: the plan stops on it, before anything is written."""
    wanted = method_files(plugin)
    recorded = read_manifest(root).get("files", {})
    steps, conflicts = [], []
    for rel, data in wanted.items():
        dest = root / rel
        if not dest.exists():
            steps.append(Step(rel, "created", _writer_bytes(dest, data)))
            continue
        current = dest.read_bytes()
        if current == data:
            steps.append(Step(rel, "kept"))
        elif recorded.get(rel) == sha(current):
            steps.append(Step(rel, "updated", _writer_bytes(dest, data)) if refresh else Step(rel, "kept"))
        else:
            conflicts.append(rel if recorded.get(rel) else f"{rel} (not written by the method)")
    for rel in sorted(set(recorded) - set(wanted) if refresh else ()):
        dest = root / rel
        if not dest.exists():
            continue
        if sha(dest.read_bytes()) == recorded[rel]:
            steps.append(Step(rel, "removed", _unlinker(root, rel)))
        else:
            conflicts.append(f"{rel} (edited, and the method no longer has it)")
    if conflicts:
        fail(EXIT_PRECONDITION, "files of .claude/ differ from the method's copy; keep your edits in "
                                "files of another name, or delete these, then run init again:\n  "
                                + "\n  ".join(conflicts))
    manifest = json.dumps({"version": version, "files": {rel: sha(d) for rel, d in sorted(wanted.items())}},
                          indent=2) + "\n"
    steps.append(file_step(root, MANIFEST, manifest, refresh))
    return steps


def _writer_bytes(path: Path, data: bytes) -> Callable[[], None]:
    def write():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return write


def _set_toml(text: str, key: str, value) -> str:
    rx = re.compile(rf'^({re.escape(key)}\s*=\s*)("(?:[^"\\]|\\.)*"|\[[^\]]*\]|[^\s#]+)', re.MULTILINE)
    literal = json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value)
    text, count = rx.subn(lambda m: m.group(1) + literal, text, count=1)
    if not count:
        fail(EXIT_ERROR, f"templates/project/delivery.toml has no '{key}' line")
    return text


def detect_forge(root: Path) -> str:
    proc = run(["git", "config", "--get", "remote.origin.url"], cwd=root, check=False)    # as written, before any rewrite rule
    url = proc.stdout.strip().lower()
    if proc.returncode != 0 or not url:
        fail(EXIT_PRECONDITION, "no 'origin' remote: add the GitHub or GitLab repository as origin first")
    for kind in ("github", "gitlab"):
        if kind in url:
            return kind
    fail(EXIT_PRECONDITION, "cannot tell the forge from the origin URL: pass --forge github|gitlab")


def agent_prefix(name: str) -> str:
    words = [w for w in re.split(r"[^a-z0-9]+", name.lower()) if w]
    prefix = words[0][:4] if len(words) == 1 else "".join(w[0] for w in words)[:4]
    return prefix or "dm"


def spec_address(root: Path, value: str, forge: str, origin: str | None = None) -> str:
    """The spec repository of an impl repository as 'git fetch' takes it: a URL or a local path
    stay as written; a short name or an owner/name is read on the forge of this repository, in
    the address style of its origin (`origin`: the address the repository is about to get)."""
    if "://" in value or re.match(r"^[\w.-]+@[\w.-]+:", value):
        return value
    local = Path(value).expanduser()
    if value.startswith((".", "/", "~")) or local.exists():
        return str(local.resolve())
    if not re.fullmatch(r"[\w.-]+(/[\w.-]+)?", value):
        fail(EXIT_ERROR, f"cannot read '{value}' as a spec repository: give a short name, owner/name, "
                         "a URL or a local path")
    if origin is None:
        origin = run(["git", "remote", "get-url", "origin"], cwd=root, check=False).stdout.strip()
    found = re.match(r"^(.*[/:])([^/:]+)/([^/]+?)(\.git)?/?$", origin)
    if not found:
        prefix, owner, suffix = f"https://{forge}.com/", "", ""
    else:
        prefix, owner, suffix = found.group(1), found.group(2), found.group(4) or ""
    if "/" in value:
        return f"{prefix}{value}{suffix}"
    if not owner:
        fail(EXIT_PRECONDITION, f"no 'origin' remote to read the owner of '{value}' from: "
                                "give owner/name, a URL or a local path")
    return f"{prefix}{owner}/{value}{suffix}"


def project_toml(root: Path, plugin: Path, args, forge: str, layout: str, origin: str | None = None) -> str:
    language = args.language or config.machine()["language"]
    if not LANGUAGE_RX.match(language):
        fail(EXIT_ERROR, f"--language takes a language code such as fr or en, got '{language}'")
    text = (plugin / "templates" / "project" / "delivery.toml").read_text(encoding="utf-8")
    values = {"repo_role": layout, "content_language": language, "forge": forge,
              "implementer": "cloud" if forge == "github" else "local",
              "agent_prefix": agent_prefix(root.name), "check": args.check or "just check",
              "acceptance": args.acceptance or "just acceptance {grep}", "serve": args.serve or "just serve {port}"}
    for key, value in values.items():
        text = _set_toml(text, key, value)
    if layout == "impl":
        address = spec_address(root, args.spec_repo, forge, origin)
        text = re.sub(r"^(repo_role\s*=.*)$", lambda m: m.group(1) + f"\nspec_source = {json.dumps(address)}"
                      + "   # le dépôt de spec que « deliveryctl spec sync » lit", text, count=1, flags=re.MULTILINE)
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
        rules += [f"Bash({launcher} story next *--go*)", f"Bash({launcher} story next *--relaunch*)"]
    return rules


def wanted_settings(plugin: Path, version: str) -> dict:
    source = {"source": "github", "repo": plugin_repo(plugin), "ref": f"{MARKETPLACE}--v{version}"}
    # the project carries its own copy of the method: a local session must not load the plugin's
    # next to it (duplicate agents, skills, commands and hooks)
    return {"enabledPlugins": {PLUGIN_KEY: False},
            "extraKnownMarketplaces": {MARKETPLACE: {"source": source}},
            "permissions": {"deny": ["SendMessage"], "ask": ask_rules()},
            "hooks": method_hooks()}


def method_hooks() -> dict:
    def entry(command: str, timeout: int) -> dict:
        return {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}
    # the filters keep the hook from running for any Bash command that is not an engine command
    pre_tool = {"matcher": "Bash", "hooks": [{"type": "command", "if": rule, "command": HOOK_PRE_TOOL, "timeout": 10}
                                              for rule in PRE_TOOL_FILTERS]}
    return {"Stop": [entry(HOOK_STOP, 40)], "SessionStart": [entry(HOOK_SESSION_START, 10)],
            "PreToolUse": [pre_tool]}


def _owned(entry) -> bool:
    return isinstance(entry, dict) and any(
        HOOK_MARK in str(h.get("command", "")) for h in entry.get("hooks") or [] if isinstance(h, dict))


def merge_hooks(merged: dict, wanted: dict, refresh: bool) -> None:
    """The method owns its hook entries (those that call 'deliveryctl hook'): init adds them where
    missing, --upgrade replaces them in place; the project's own hooks are never touched."""
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return
    for event, entries in wanted.items():
        current = hooks.get(event)
        if not isinstance(current, list):
            hooks[event] = copy.deepcopy(entries)
        elif not any(_owned(e) for e in current):
            current += copy.deepcopy(entries)
        elif refresh:
            fresh = iter(copy.deepcopy(entries))
            hooks[event] = [next(fresh, None) if _owned(e) else e for e in current]
            hooks[event] = [e for e in hooks[event] if e is not None]


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
    init only adds its ref, and --upgrade refreshes it. Both disable the plugin in the project;
    --upgrade also replaces the method's hooks."""
    merged = copy.deepcopy(current)
    wanted = dict(wanted)
    merge_hooks(merged, wanted.pop("hooks"), refresh)
    ref = wanted["extraKnownMarketplaces"][MARKETPLACE]["source"]["ref"]
    known = merged.get("extraKnownMarketplaces")
    entry = known.get(MARKETPLACE) if isinstance(known, dict) else None
    if isinstance(entry, dict):
        wanted = {k: v for k, v in wanted.items() if k != "extraKnownMarketplaces"}
        source = entry.get("source")
        pinned = isinstance(source, dict) and ("ref" in source or source.get("source") in ("github", "git"))
        if pinned and (refresh or "ref" not in source):
            source["ref"] = ref
    # the method owns this key: a project-scope plugin install writes it as true before init runs
    plugins = merged.setdefault("enabledPlugins", {})
    if isinstance(plugins, dict):
        plugins[PLUGIN_KEY] = False
    wanted.pop("enabledPlugins")
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
        text = (source / rel).read_text(encoding="utf-8")
        if rel == "spec.toml":
            text = _set_toml(text, "name", root.name)
        steps.append(file_step(root, dest, text))
    steps.append(file_step(root, "spec/CHANGELOG.md", "# Changelog de la spécification\n"))
    steps.append(file_step(root, "spec/product/brief.md", (source / "brief.md").read_text(encoding="utf-8")))
    steps.append(file_step(root, "spec/product/glossary.md", "# Glossaire\n"))
    return steps


GITLAB_INCLUDE = "- local: .gitlab/delivery-ci.yml"
INCLUDE_ALIAS_RX = re.compile(r"(^|\s)[&*]\w|!reference|<<:")


def with_include(text: str) -> str | None:
    """`.gitlab-ci.yml` with the include of the method's CI added, editing nothing else; None when
    its `include:` is not a block-style list (a string, a flow list, anchors) and the owner must
    add the item."""
    eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    at = next((i for i, line in enumerate(lines) if re.match(r"^include:\s*(#.*)?$", line)), None)
    if at is None:
        if any(re.match(r"^include\s*:", line) for line in lines):
            return None
        lines += ([""] if lines and lines[-1].strip() else []) + ["include:", "  " + GITLAB_INCLUDE]
        return eol.join(lines) + eol
    last, indent = None, None
    for i in range(at + 1, len(lines)):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] not in " \t-":
            break
        if indent is None:
            item = re.match(r"^(\s*)-(\s|$)", line)
            if not item:
                return None
            indent = item.group(1)
        if INCLUDE_ALIAS_RX.search(line):
            return None
        last = i
    if indent is None or INCLUDE_ALIAS_RX.search(lines[at]):
        return None
    lines.insert(last + 1, indent + GITLAB_INCLUDE)
    return eol.join(lines) + eol


def gitlab_include_step(root: Path, notes: list[str]) -> Step:
    """The include of the method's CI in the project's own `.gitlab-ci.yml`."""
    path = root / ".gitlab-ci.yml"
    if not path.exists():
        return Step(".gitlab-ci.yml", "created", _writer(path, "include:\n  " + GITLAB_INCLUDE + "\n"))
    text = path.read_text(encoding="utf-8")
    if ".gitlab/delivery-ci.yml" in text:
        return Step(".gitlab-ci.yml", "kept")
    new = with_include(text)
    if new is None:
        notes.append(".gitlab-ci.yml is left as it is (its include is not a block-style list): add to it\n"
                     "      include:\n        " + GITLAB_INCLUDE)
        return Step(".gitlab-ci.yml", "kept")
    return Step(".gitlab-ci.yml", "merged", _writer(path, new))


def split_names(args) -> None:
    """The words after the layout: `impl` takes the spec repository, then a name; the others a name."""
    names = list(args.names or [])
    args.layout = args.layout or ""
    args.spec_repo = args.name = None
    if args.layout == "impl":
        if not names:
            fail(EXIT_ERROR, "usage: deliveryctl init impl <spec repository> [name] "
                             "(the spec repository: a short name, owner/name, a URL or a local path)")
        args.spec_repo, args.name = names[0], (names[1] if len(names) > 1 else None)
        extra = names[2:]
    else:
        args.name, extra = (names[0] if names else None), names[1:]
    if extra:
        fail(EXIT_ERROR, f"usage: deliveryctl init {args.layout or 'single'} "
                         + ("<spec repository> [name]" if args.layout == "impl" else "[name]")
                         + f": unexpected '{extra[0]}'")


def install_steps(root: Path, plugin: Path, version: str, args, notes: list[str],
                  target: create.Target | None = None) -> tuple[list[Step], str, str]:
    toml_path = root / config.PROJECT_FILE
    answers = [f"--{k}" for k in ("language", "forge", "check", "acceptance", "serve") if getattr(args, k, None)]
    answers += [v for v in (args.layout, args.spec_repo) if v]
    if toml_path.exists():
        cfg = config.load(root)
        forge, layout = cfg.forge, cfg.repo_role
        if answers:
            notes.append(f"delivery.toml exists: {', '.join(answers)} ignored (edit the file)")
        steps = [Step("delivery.toml", "kept")]
    else:
        layout = args.layout or "single"
        if layout == "impl" and not args.spec_repo:
            fail(EXIT_ERROR, "usage: deliveryctl init impl <spec repository> "
                             "(a short name, owner/name, a URL or a local path)")
        if not args.layout:
            notes.append("layout = single, spec and code in this repository (init spec or init impl <spec> to choose)")
        forge = target.forge if target else args.forge or detect_forge(root)
        if not args.forge and not target:
            notes.append(f"forge = {forge}, read from the origin remote (--forge to choose)")
        steps = [Step("delivery.toml", "created",
                      _writer(toml_path, project_toml(root, plugin, args, forge, layout,
                                                      target.origin_url() if target else None)))]
    existing = copy_version(root)
    if existing and existing != version:
        notes.append(f"engine copy {existing}, plugin {version}: 'deliveryctl init --upgrade' refreshes it")
    steps += engine_steps(root, plugin, version, refresh=False)
    steps += method_steps(root, plugin, version, refresh=False)
    steps.append(claude_md_step(root, plugin))
    steps.append(settings_step(root, plugin, existing or version, refresh=False))
    steps.append(gitignore_step(root))
    justfile = next((p.name for p in root.iterdir() if p.name.lower() in ("justfile", ".justfile")), "") \
        if root.is_dir() else ""
    template = "justfile-spec" if layout == "spec" else "justfile"
    steps.append(Step(justfile, "kept") if justfile else template_step(root, plugin, "justfile", template))
    if layout in ("spec", "single"):
        steps += spec_steps(root, plugin)
    if forge == "github":
        steps.append(template_step(root, plugin, ".github/workflows/delivery.yml", "github-ci.yml"))
    elif forge == "gitlab":
        steps.append(template_step(root, plugin, ".gitlab/delivery-ci.yml", "gitlab-ci.yml"))
        steps.append(gitlab_include_step(root, notes))
    return steps, forge, layout


# -- the plan: what init will do, known before anything is written -------------------------------
@dataclass
class Plan:
    root: Path
    steps: list[Step]
    forge: str
    layout: str
    branch: str
    version: str
    upgrade: bool
    notes: list[str] = field(default_factory=list)
    target: create.Target | None = None       # the repository to create; None = origin exists
    git_repo: bool = True                     # False: `git init` first
    found: str = ""                           # the origin found: 'owner/name', or its address
    previous: str = ""                        # upgrade: the version of the engine copy
    visibility: str = ""                      # of the repository found; '' = the forge did not say
    address: str = ""                         # the git address to set before the commit
    protect: bool = False

    @property
    def changed(self) -> list[Step]:
        return [s for s in self.steps if s.status != "kept"]


def is_repo(root: Path) -> bool:
    return root.is_dir() and run(["git", "rev-parse", "--git-dir"], cwd=root, check=False).returncode == 0


def locate(args) -> tuple[Path, bool]:
    """The folder init works in, and whether it is already a git repository. A name makes a new
    folder; without one, the current repository, or the current folder."""
    if args.name:
        root = Path.cwd() / args.name
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            line = f"cd {args.name} && deliveryctl init {args.layout or 'single'}" \
                   + (f" {args.spec_repo}" if args.spec_repo else "")
            fail(EXIT_PRECONDITION, f"{args.name} exists and is not empty: to equip it, type: {line}")
        return root, False
    top = run(["git", "rev-parse", "--show-toplevel"], cwd=Path.cwd(), check=False)
    if top.returncode != 0:
        return Path.cwd(), False
    root = Path(top.stdout.strip())
    if root.resolve() != main_root().resolve():
        fail(EXIT_PRECONDITION, "run init in the main checkout, not in a story worktree")
    return root, True


def current_branch(root: Path) -> str:
    return run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=root, check=False).stdout.strip()


def machine_email(root: Path) -> str:
    where = root if root.is_dir() else Path.cwd()
    return run(["git", "config", "user.email"], cwd=where, check=False).stdout.strip()


def install_plan(args, plugin: Path, version: str) -> Plan:
    split_names(args)
    notes: list[str] = []
    root, git_repo = locate(args)
    machine = config.machine()
    has_origin = git_repo and bool(run(["git", "remote", "get-url", "origin"], cwd=root, check=False).stdout.strip())
    target, found, visibility = None, "", ""
    chosen = args.visibility or machine["visibility"]
    if has_origin:
        if args.visibility:
            notes.append(f"--{args.visibility} ignored: the repository exists, its visibility is read from the forge")
    else:
        toml = root / config.PROJECT_FILE
        forge = config.load(root).forge if toml.exists() else (args.forge or machine["forge"])
        target = create.resolve(forge, root.name, chosen, machine)
    steps, forge, layout = install_steps(root, plugin, version, args, notes, target)
    if target:
        branch = current_branch(root) if git_repo else "main"
        branch = branch or "main"
    else:
        git = Git(root)
        branch, default = current_branch(root), git.target_branch()
        if branch != default:
            fail(EXIT_PRECONDITION, f"init commits on the default branch ({default}) and this one is {branch or 'detached'}: "
                                    f"git switch {default}")
        info = Forge(None, git, forge).repo()
        found, visibility = info["path"] or run(["git", "remote", "get-url", "origin"], cwd=root).stdout.strip(), \
            info["visibility"]
    plan = Plan(root, steps, forge, layout, branch, version, False, notes, target, git_repo, found=found,
                visibility=visibility)
    plan.protect = bool(target or plan.changed)
    if forge == "github" and (target.visibility if target else visibility) == "public":
        plan.address = public_address(plan, machine_email(root))
    return plan


def public_address(plan: Plan, current: str) -> str:
    """The noreply address a public GitHub repository publishes in every commit; '' when the
    configured one already is a noreply address, or the forge does not tell who the owner is."""
    if current.lower().endswith(create.NOREPLY):
        return ""
    try:
        login, uid = (plan.target.login, plan.target.uid) if plan.target else create.github_user()
    except DeliveryError as exc:
        plan.notes.append(f"git address left as it is: {exc.message}")
        return ""
    return create.noreply(login, uid) if uid else ""


def upgrade_plan(plugin: Path, version: str) -> Plan:
    root = repo_root()
    if root.resolve() != main_root().resolve():
        fail(EXIT_PRECONDITION, "run init in the main checkout, not in a story worktree")
    if not (root / config.PROJECT_FILE).exists():
        fail(EXIT_PRECONDITION, "delivery.toml not found: run 'deliveryctl init' first")
    existing = copy_version(root)
    if existing and version_key(existing) > version_key(version):
        fail(EXIT_PRECONDITION, f"the project engine {existing} is newer than the plugin {version}: "
                                "update the plugin first")
    steps = engine_steps(root, plugin, version, refresh=True)
    steps += method_steps(root, plugin, version, refresh=True)
    steps.append(settings_step(root, plugin, version, refresh=True))
    steps.append(gitignore_step(root))
    git = Git(root)
    cfg = config.load(root)
    return Plan(root, [s for s in steps if s], cfg.forge, cfg.repo_role, current_branch(root) or git.target_branch(),
                version, True, [], previous=existing)


def summary(plan: Plan) -> list[str]:
    """What init is about to do, in a few lines (before any write)."""
    lines = [f"Dossier : {plan.root}"]
    if plan.upgrade:
        lines.append(f"Mise à jour : delivery-method {plan.previous or '?'} → {plan.version}")
    elif plan.target:
        t = plan.target
        lines.append(f"Dépôt : créer {t.path} sur {t.where}, {VISIBILITY_FR[t.visibility]}")
    else:
        lines.append(f"Dépôt : origin {plan.found}" + (f" ({VISIBILITY_FR[plan.visibility]})" if plan.visibility in VISIBILITY_FR
                                                      else ", visibilité inconnue"))
    if not plan.upgrade:
        lines.append(f"Disposition : {plan.layout}")
        lines.append("Adresse git : " + (plan.address or "inchangée"))
    lines.append(f"Commit et push sur {plan.branch}")
    if plan.protect:
        required = "CI exigée" if plan.layout == "spec" else "CI exigée après la première fusion"
        merges = "demande de fusion obligatoire, commits de fusion seuls"
        lines.append(f"Protection de {plan.branch} : {merges}, {required}")
    return lines


VISIBILITY_FR = {"private": "privé", "public": "public", "internal": "interne"}
YES = ("o", "oui", "y", "yes")


def confirm(args) -> bool | None:
    """One question; only o, oui, y or yes go on. None: no terminal to ask on, and no --yes."""
    if args.yes:
        return True
    if not sys.stdin or not sys.stdin.isatty():
        return None
    try:
        answer = input("Continuer ? [o/N] ")
    except EOFError:
        answer = ""
    return answer.strip().lower() in YES


def commit_paths(root: Path, steps: list[Step]) -> list[str]:
    """The paths init laid down, as git takes them: those still on disk, or tracked (a removed copy)."""
    git, paths = Git(root), []
    for step in steps:
        path = step.path.rstrip("/")
        if step.status != "kept" and (step.status != "removed" or git.out("ls-files", "--", path, check=False)):
            paths.append(path)
    return paths


def apply(plan: Plan) -> tuple[str, list[str]]:
    """Write the plan, then the forge gestures; returns what became of the commit ('pushed',
    'local' when the push was refused, 'none' when the files equal the last commit) and the notes."""
    root, notes = plan.root, []
    root.mkdir(parents=True, exist_ok=True)
    if not plan.git_repo:
        run(["git", "init", "--quiet", "--initial-branch", plan.branch], cwd=root)
    if plan.target:
        create.create(root, plan.target)
    if plan.address:
        run(["git", "config", "user.email", plan.address], cwd=root)
    for step in plan.steps:
        if step.write:
            step.write()
    git = Git(root)
    subject = (f"Met à jour delivery-method vers {plan.version}" if plan.upgrade
               else f"Équipe le dépôt avec delivery-method {plan.version} ({plan.layout})")
    paths = commit_paths(root, plan.steps)
    git.run("add", "--", *paths)
    if git.ok("diff", "--cached", "--quiet", "--", *paths):
        return "none", notes
    git.commit(paths, subject, trailers=[("Delivery-Method", plan.version)], only=True)
    try:
        git.push(plan.branch)
    except DeliveryError as exc:
        detail = exc.message.splitlines()[-1] if exc.message else ""
        notes.append(f"push refused ({detail}): the commit stays local; push it with 'git push -u origin {plan.branch}' "
                     "or, on a protected branch, from a branch and a merge request")
        return "local", notes
    git.run("remote", "set-head", "origin", plan.branch, check=False)
    if plan.protect:
        try:
            notes += Forge(config.load(root), git).protect(plan.branch, checks=plan.layout == "spec")
        except DeliveryError as exc:
            notes.append(f"protection of {plan.branch} skipped: {exc.message}")
    return "pushed", notes


def next_steps(root: Path, steps: list[Step], forge: str, layout: str, upgrade: bool,
               branch: str = "", outcome: str = "pushed") -> list[str]:
    """The lines a human needs now, in order: what was laid down, the next command."""
    changed = [s for s in steps if s.status != "kept"]
    if not changed:
        return ["Rien à changer : le dépôt est déjà équipé. Diagnostic : .delivery/deliveryctl doctor"]
    done = {"pushed": f"commités et poussés sur {branch}", "local": f"commités sur {branch}, push à refaire",
            "none": "écrits, identiques au dernier commit"}[outcome]
    if upgrade:
        return [f"{len(changed)} fichiers mis à jour, {done}"]
    lines = [f"{len(changed)} fichiers posés, {done}"]
    brief = next((s for s in steps if s.path == "spec/product/brief.md"), None)
    if layout == "impl":
        lines.append("Une fois la spec publiée : .delivery/deliveryctl spec sync <version> (sa source est connue)")
    elif brief and brief.status == "created":
        lines.append("Ensuite : claude --agent product-analyst, puis /brainstorm --vision <votre idée>")
    else:
        lines.append("Ensuite : claude --agent product-analyst, puis /spec-frame <incrément>")
    mode = run(["git", "config", "--get", "core.fileMode"], cwd=root, check=False).stdout.strip()
    if mode == "false" and any(s.path.startswith(".delivery/") for s in changed):
        lines.append("git update-index --chmod=+x .delivery/deliveryctl   (ce système de fichiers "
                     "ne garde pas le bit exécutable)")
    return lines


def diagnosis(root: Path) -> list[str]:
    """The `note` and `warn` lines of doctor for the equipped repository; nothing when all is ok."""
    from . import doctor
    here = os.getcwd()
    os.chdir(root)
    try:
        return [f"{level}: {message}" for level, message in doctor.collect() if level != "ok"]
    finally:
        os.chdir(here)


def main(args) -> int:
    plugin = plugin_source()
    version = engine_version(plugin)
    plan = upgrade_plan(plugin, version) if args.upgrade else install_plan(args, plugin, version)
    print(f"deliveryctl init{' --upgrade' if args.upgrade else ''} (plugin {version})"
          + (" — dry run, nothing written" if args.dry_run else ""))
    pending = bool(plan.changed or plan.target)
    if pending:
        for line in summary(plan):
            print(line)
    if args.dry_run or not pending:
        for step in plan.steps:
            print(f"  {step.status:8} {step.path}")
        for note in plan.notes:
            print(f"note: {note}")
        if args.dry_run:
            print("\nRelancez sans --dry-run pour appliquer.")
            return EXIT_OK
    else:
        answer = confirm(args)
        if answer is None:
            print("Pas de terminal pour répondre : relancez avec --yes pour continuer. Rien n'a été écrit.")
            return EXIT_PRECONDITION
        if not answer:
            print("Rien n'a été écrit.")
            return EXIT_OK
    outcome = "pushed"
    if pending:
        outcome, forge_notes = apply(plan)
        for step in plan.steps:
            print(f"  {step.status:8} {step.path}")
        for note in plan.notes + forge_notes:
            print(f"note: {note}")
    for line in diagnosis(plan.root):
        print(line)
    print("\nProchaines étapes :")
    for line in next_steps(plan.root, plan.steps, plan.forge, plan.layout, args.upgrade, plan.branch, outcome):
        print("  " + line)
    return EXIT_TOOL if outcome == "local" else EXIT_OK
