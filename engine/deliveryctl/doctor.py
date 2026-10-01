"""`deliveryctl doctor`: read-only diagnosis of the project and of this machine. Each line is
'ok', 'note' (a recommendation) or 'warn' (something to fix); the verb always exits 0."""

from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from . import cards, config, init, journal, roles
from . import verdict as vd
from .core import EXIT_OK, DeliveryError, is_cloud, main_root
from .gitops import Git, worktree_path
from .window import mentions

ACCEPTED = ("accepted", "accepted-with-reserves")
VERSION_TAG_RX = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
BUILTINS = ("cd", "export", "set", "source", ".", "exec", "env")


class Context:
    root: Path | None = None
    git: Git | None = None
    cfg: config.Config | None = None
    plugin: Path | None = None


def _get(data, *keys):
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").splitlines())


def _probe(argv: list[str], timeout: int, env: dict | None = None) -> bool:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL, env={**os.environ, **(env or {})})
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


# -- checks ---------------------------------------------------------------------------------
def check_repository(ctx):
    try:
        ctx.root = main_root()
    except DeliveryError:
        yield "warn", "not inside a git repository: project checks skipped"
        return
    ctx.git = Git(ctx.root)
    yield "ok", f"repository {ctx.root}"


def check_plugin(ctx):
    if is_cloud():
        return
    ctx.plugin = roles.plugin_root()
    if ctx.plugin:
        yield "ok", f"plugin {ctx.plugin}"
    else:
        yield "warn", "plugin not found: set plugin_dir in ~/.config/delivery-method/machine.toml"


def check_engine(ctx):
    if is_cloud():
        copy = init.copy_version(ctx.root)
        yield ("ok", f"engine copy {copy}") if copy else ("warn", "no engine copy in .delivery/: run 'deliveryctl init'")
        return
    copy = init.copy_version(ctx.root)
    if not copy:
        yield "warn", "no engine copy in .delivery/: run 'deliveryctl init'"
        return
    plugin = init.engine_version(ctx.plugin) if init.is_plugin(ctx.plugin) else ""
    engine = ctx.root / ".delivery" / "engine" / "deliveryctl"
    if plugin and plugin != copy:
        remedy = "update the plugin" if init.version_key(copy) > init.version_key(plugin) else \
            "'deliveryctl init --upgrade', review, commit"
        yield "warn", f"engine copy {copy}, plugin {plugin}: {remedy}"
    elif plugin and init.digest(engine) != init.digest(ctx.plugin / "engine" / "deliveryctl"):
        yield "warn", f"engine copy {copy} differs from the plugin at the same version: 'deliveryctl init --upgrade' restores it"
    else:
        yield "ok", f"engine copy {copy}"
    staged = ctx.git.out("ls-files", "--stage", "--", ".delivery/deliveryctl", check=False)
    if staged and not staged.startswith("100755"):
        yield "warn", ".delivery/deliveryctl is not executable in git: git update-index --chmod=+x .delivery/deliveryctl"


def check_method(ctx):
    """The project copy of the agents, skills and commands, against the manifest written with it."""
    manifest = init.read_manifest(ctx.root)
    if not manifest:
        yield "warn", "no .delivery/method.json: the project does not carry the method's agents, skills and commands: 'deliveryctl init --upgrade'"
        return
    problems = []
    copy = init.copy_version(ctx.root)
    if manifest.get("version") != copy:
        problems.append(f"method copy {manifest.get('version')}, engine copy {copy or 'absent'}")
    for rel, sha in sorted(manifest["files"].items()):
        path = ctx.root / rel
        if not path.exists():
            problems.append(f"{rel} is missing")
        elif init.sha(path.read_bytes()) != sha:
            problems.append(f"{rel} was edited")
    for problem in problems:
        yield "warn", f"method copy: {problem}: 'deliveryctl init --upgrade' restores it"
    if not problems:
        yield "ok", f"method copy {manifest['version']} ({len(manifest['files'])} files in .claude/)"


def check_project(ctx):
    ctx.cfg = config.load(ctx.root)
    yield "ok", f"delivery.toml (repo_role {ctx.cfg.repo_role}, forge {ctx.cfg.forge})"


def check_machine(ctx):
    if is_cloud():
        yield "note", ("cloud session: machine settings, the window, the notification command and the plugin "
                       "are the owner's computer's, not checked here")
        return
    machine = config.machine()
    path = config.machine_path()
    yield "ok", f"machine settings ({path if path.exists() else 'defaults'})"
    cmd = machine["notify_cmd"]
    if not cmd:
        yield "note", "notify_cmd is empty: notifications only reach the engine's error output"
    elif not os.access(os.path.expanduser(cmd), os.X_OK):
        yield "note", f"notify_cmd '{cmd}' is not an executable file: notifications fall back to the error output"
    dsn = machine["journal_dsn"]
    if not dsn:
        return
    if not shutil.which("psql"):
        yield "warn", "journal_dsn is set but psql is not installed: events wait in the local queue"
    elif not _probe(["psql", "-X", "-q", "-w", "-c", "select 1"], 5, journal.psql_env(dsn)):
        yield "warn", "journal database unreachable (psql -c 'select 1'): events wait in the local queue"
    else:
        yield "ok", "journal database reachable"
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    queue = Path(base) / "delivery-method" / "journal-queue.jsonl"
    queued = _lines(queue) if queue.exists() else 0
    if queued:
        yield "note", f"{queued} journal event(s) queued locally: deliveryctl journal flush"


def check_remote(ctx):
    if not ctx.git.has_remote():
        yield "warn", "no 'origin' remote: story branches cannot be pushed nor merge requests opened"
        return
    proc = ctx.git.run("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False)
    if proc.returncode == 0:
        yield "ok", f"origin, target branch {proc.stdout.strip()}"
    else:
        yield "warn", "origin/HEAD is not set: git remote set-head origin --auto"


def check_gitignore(ctx):
    path = ctx.root / ".gitignore"
    missing = init.missing_gitignore(path.read_text(encoding="utf-8") if path.exists() else "")
    if missing:
        yield "warn", f".gitignore lacks {', '.join(missing)}: deliveryctl init adds them"
    else:
        yield "ok", ".gitignore"


def check_claude_md(ctx):
    path = ctx.root / "CLAUDE.md"
    if not path.exists():
        yield "warn", "CLAUDE.md missing: deliveryctl init creates it"
    elif not any(line.strip() == init.RULES_IMPORT for line in path.read_text(encoding="utf-8").splitlines()):
        yield "warn", f"CLAUDE.md does not import {init.RULES_IMPORT}"
    else:
        yield "ok", "CLAUDE.md imports the common rules"
    if path.exists() and _lines(path) > 40:
        yield "note", f"CLAUDE.md has {_lines(path)} lines (above 40): every session loads it; move details to docs/"
    home = Path.home() / ".claude" / "CLAUDE.md"
    if home.exists() and _lines(home) > 60:
        yield "note", f"~/.claude/CLAUDE.md has {_lines(home)} lines (above 60): every session on this machine loads it"


def check_settings(ctx):
    path = ctx.root / ".claude" / "settings.json"
    if not path.exists():
        yield "warn", ".claude/settings.json missing: deliveryctl init creates it"
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        yield "warn", f".claude/settings.json is not valid JSON: {exc}"
        return
    problems = []
    if _get(data, "enabledPlugins", init.PLUGIN_KEY) is not False:
        problems.append(f"enabledPlugins does not disable {init.PLUGIN_KEY} (the project carries its own copy)")
    for event, command in (("Stop", init.HOOK_STOP), ("SessionStart", init.HOOK_SESSION_START)):
        entries = _get(data, "hooks", event)
        if not any(isinstance(h, dict) and h.get("command") == command
                   for e in entries if isinstance(e, dict) for h in e.get("hooks") or []
                   ) if isinstance(entries, list) else True:
            problems.append(f"the {event} hook is missing")
    if "SendMessage" not in (_get(data, "permissions", "deny") or []):
        problems.append("SendMessage is not denied")
    for problem in problems:
        yield "warn", f".claude/settings.json: {problem}: 'deliveryctl init --upgrade' fixes it"
    if not problems:
        yield "ok", ".claude/settings.json"
    ref = _get(data, "extraKnownMarketplaces", init.MARKETPLACE, "source", "ref")
    copy = init.copy_version(ctx.root)
    if ref and copy and ref != f"{init.MARKETPLACE}--v{copy}":
        yield "note", f"marketplace ref {ref}, engine copy {copy}: 'deliveryctl init --upgrade' aligns them"


def _executable(command: str) -> str:
    """First program of a command line, after leading VAR=value words; '' for a builtin."""
    try:
        words = shlex.split(command)
    except ValueError:
        return ""
    while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
        words.pop(0)
    return words[0] if words and words[0] not in BUILTINS else ""


def check_claude(ctx):
    if is_cloud():
        return
    if shutil.which("claude"):
        yield "ok", "claude CLI"
    else:
        yield "warn", "claude CLI not found: role sessions cannot start"


def check_tools(ctx):
    cfg = ctx.cfg
    if not cfg:
        return
    tool = {"github": "gh", "gitlab": "glab"}.get(cfg.forge)
    if tool and not shutil.which(tool):
        yield "warn", f"forge = {cfg.forge} needs the '{tool}' command"
    elif tool and not _probe([tool, "auth", "status"], 15):
        yield "warn", f"'{tool} auth status' fails: {tool} auth login"
    elif tool:
        yield "ok", f"{tool} authenticated"
    for name, command in cfg.commands.items():
        exe = _executable(command)
        if exe and not shutil.which(exe) and not (ctx.root / exe).exists():
            yield "warn", f"commands.{name}: '{exe}' not found"


def _origin_host(url: str) -> str:
    """Host of a git remote URL (https, ssh:// or scp-like), lower case."""
    url = url.strip().lower()
    if "://" in url:
        url = url.split("://", 1)[1]
    return url.rsplit("@", 1)[-1].split("/", 1)[0].split(":", 1)[0]


def check_cloud(ctx):
    """With implementer = cloud, the story-implementer runs as a Claude Code cloud session."""
    cfg = ctx.cfg
    if is_cloud() or not cfg or cfg.implementer != "cloud":
        return
    if shutil.which("claude"):
        try:
            proc = subprocess.run(["claude", "auth", "status", "--json"], capture_output=True, text=True,
                                  timeout=15, stdin=subprocess.DEVNULL)
            status = json.loads(proc.stdout or "{}")
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            status = {}
        status = status if isinstance(status, dict) else {}
        if status.get("loggedIn") is True and status.get("authMethod") == "claude.ai":
            yield "ok", "claude logged in with claude.ai (cloud sessions)"
        else:
            yield "warn", ("implementer = cloud needs 'claude auth status --json' to say loggedIn with "
                           "authMethod claude.ai: claude auth login")
    proc = ctx.git.run("remote", "get-url", "origin", check=False)
    if proc.returncode == 0 and _origin_host(proc.stdout) != "github.com":
        yield "warn", (f"implementer = cloud: origin ({proc.stdout.strip()}) is not on github.com, "
                       "a cloud session works on GitHub only")
    yield "note", ("implementer = cloud: cloud sessions run in the default environment chosen by /remote-env "
                   "in Claude Code; it must reach the project's toolchain (README)")


def check_ci(ctx):
    """With a forge, merges wait for a green CI: a CI that never starts blocks them silently."""
    cfg = ctx.cfg
    if not cfg or cfg.forge not in ("github", "gitlab"):
        return
    if cfg.forge == "github":
        path, remedy = ".github/workflows/delivery.yml", "'deliveryctl init' lays it"
        missing = not (ctx.root / path).exists()
    else:
        path, remedy = ".gitlab-ci.yml", "add 'include: [{local: .gitlab/delivery-ci.yml}]'"
        main_ci = ctx.root / path
        missing = ".gitlab/delivery-ci.yml" not in (main_ci.read_text(encoding="utf-8", errors="replace")
                                                    if main_ci.exists() else "")
    if missing:
        what = "is missing" if cfg.forge == "github" else "does not include .gitlab/delivery-ci.yml"
        yield "warn", (f"{path} {what}: no CI runs on merge requests, and a merge waits for a green CI "
                       f"({remedy})")
        return
    files = [path] + ([".gitlab/delivery-ci.yml"] if cfg.forge == "gitlab" else [])
    untracked = [f for f in files if not ctx.git.out("ls-files", "--", f, check=False)]
    if untracked:
        yield "warn", f"{', '.join(untracked)} not committed: the forge does not see the CI"
    else:
        yield "ok", f"CI of merge requests ({path})"


def _trusted() -> set[str] | None:
    """Folders where Claude Code's trust dialog was accepted; None when unknown."""
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    path = Path(base) / ".claude.json" if base else Path.home() / ".claude.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, dict):
        return None
    return {str(k).rstrip("/") for k, v in projects.items()
            if isinstance(v, dict) and v.get("hasTrustDialogAccepted") is True}


def check_trust(ctx):
    """An interactive role session in a story worktree waits on the trust dialog when neither
    the repository (whose trust the worktrees inherit) nor the worktrees folder is trusted."""
    if is_cloud():
        return
    terminal = config.machine().get("window") == "terminal"       # headless sessions: no dialog
    trusted = _trusted() if shutil.which("claude") and not terminal else None
    if trusted is None:
        return
    worktrees = worktree_path(ctx.root, "x").parent
    places = {str(p).rstrip("/") for p in (ctx.root, ctx.root.resolve(), worktrees, worktrees.resolve())}
    if not places & trusted:
        yield "note", (f"Claude Code has no accepted trust for {ctx.root}: start 'claude' once in it and "
                       "accept the trust dialog, or interactive role sessions wait on it in the worktrees")


def check_worktrees(ctx):
    open_ids = [str(i.get("branch", "")).rsplit("/", 1)[-1] for i in ctx.git.worktrees()
                if str(i.get("branch", "")).startswith("refs/heads/story/")]
    if not open_ids:
        return
    merged = cards.merged_ids(ctx.git)
    for card_id in open_ids:
        if card_id in merged:
            yield "note", (f"{cards.label_of(ctx.git, card_id)} is merged but its worktree remains: "
                           f"deliveryctl story close {card_id}")


def check_location(ctx):
    wsl = "microsoft" in platform.release().lower() or "WSL_DISTRO_NAME" in os.environ
    if wsl and str(ctx.root.resolve()).startswith("/mnt/"):
        yield "note", ("working copy under /mnt/: prefer the Linux filesystem for working copies, "
                       "faster and more robust")


def _accepted_trees(git: Git, revs: list[str]) -> set[str]:
    trees = set()
    for rev in revs:
        names = git.out("ls-tree", "--name-only", rev, "qualification/reports/", check=False).splitlines()
        for name in names:
            parsed = vd.parse(git.show(rev, name), "qualification") if name.endswith(".md") else None
            if parsed and parsed.valid and parsed.verdict in ACCEPTED:
                trees.add(parsed.tree)
    return trees


def _covered(git: Git, tag: str, accepted: set[str]) -> bool:
    """The tag, or an ancestor it differs from by qualification or story files only (the
    report merged before the tag), has an accepted report for its code tree."""
    rev = tag
    for _ in range(10):
        if git.code_tree(rev) in accepted:
            return True
        proc = git.run("diff", "--name-only", f"{rev}^1", rev, check=False)
        names = proc.stdout.splitlines()
        if proc.returncode != 0 or not names or \
                any(not n.startswith(("qualification/", "docs/stories/")) for n in names):
            return False
        rev = f"{rev}^1"
    return False


def check_releases(ctx):
    cfg = ctx.cfg
    if not cfg or cfg.repo_role == "spec":
        return
    tags = [t for t in ctx.git.out("tag", "--list", "--sort=-creatordate").splitlines()
            if VERSION_TAG_RX.match(t)][:10]
    if not tags:
        if cfg.release_stage == "released":
            yield "note", "release_stage = released but no version tag"
        return
    try:
        target = [ctx.git.target_ref()]
    except DeliveryError:
        target = []
    accepted = _accepted_trees(ctx.git, target + tags)
    for tag in tags:
        if not _covered(ctx.git, tag, accepted):
            yield "note", f"tag {tag} has no accepted qualification report for its code tree"


def check_mentions(ctx):
    for path in mentions.files_naming_it(ctx.root)[:5]:
        shown = path.relative_to(ctx.root) if path.is_relative_to(ctx.root) else path
        yield "note", (f"{shown} names the terminal multiplexer: keep the runtime environment out of "
                       "project instructions (the engine alone drives windows)")


GLOBAL = (check_repository, check_plugin, check_machine, check_claude)
PROJECT = (check_engine, check_method, check_project, check_remote, check_gitignore, check_claude_md, check_settings,
           check_tools, check_cloud, check_ci, check_trust, check_worktrees, check_location, check_releases, check_mentions)


def main(args) -> int:
    ctx = Context()
    for check in GLOBAL + PROJECT:
        if check in PROJECT and ctx.root is None:
            continue
        try:
            for level, message in check(ctx):
                print(f"{level}: {message}")
        except DeliveryError as exc:
            print(f"warn: {exc.message}")
    return EXIT_OK
