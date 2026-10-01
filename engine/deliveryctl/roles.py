"""Role sessions: generated permission files and launch contract (CONTRACTS.md §11.1)."""

from __future__ import annotations

import json
import os
import shlex
import uuid
from pathlib import Path

from . import VERSION, config
from . import frontmatter as fm
from .config import Config
from .core import EXIT_ERROR, EXIT_PRECONDITION, ROLES, fail, run_dir, write_json
from .gitops import worktree_path

PLUGIN = "delivery-method"
UNATTENDED = ("technical-lead", "story-implementer", "story-reviewer", "qualification-runner")

DENY_TOOLS = ["Agent", "Workflow", "SendMessage", "Monitor", "CronCreate", "CronDelete",
              "RemoteTrigger", "PushNotification", "AskUserQuestion", "WebSearch"]
READ_ONLY_SHELL = ["ls", "cat", "head", "tail", "wc", "grep", "rg", "find", "sort", "uniq",
                   "diff", "jq", "tree", "pwd", "echo", "test", "stat", "file", "which", "date",
                   "printenv"]
GIT_READ = ["git status", "git diff", "git log", "git show", "git ls-files", "git blame",
            "git rev-parse", "git branch --show-current", "git worktree list", "git grep",
            "git merge-base", "git ls-tree"]
GIT_WRITE = ["git add", "git commit", "git rm", "git mv", "git restore"]
ENGINE_READ = ["deliveryctl story status", "deliveryctl cards list", "deliveryctl cards order",
               "deliveryctl cards lint"]
DENY_BASH = ["git push", "git reset --hard", "git clean", "git rebase", "git checkout --",
             "git branch -D", "git stash drop", "git commit --amend", "herdr",
             "deliveryctl run", "deliveryctl merge", "deliveryctl note", "deliveryctl journal",
             "deliveryctl spec release", "deliveryctl spec sync", "deliveryctl init",
             "deliveryctl nightly", "deliveryctl qualify submit", "claude"]
SECRET_READS = ["~/.ssh/**", "~/.config/gh/**", "~/.config/glab-cli/**", "**/.env.secrets",
                "~/.local/state/delivery-method/**"]
# archived brainstorms stay outside every decision (skill brainstorm)
ARCHIVE = "docs/maybe"
PROTECTED = ["spec/**", "spec.lock", ".delivery/**", ".claude/**", "delivery.toml", "CLAUDE.md",
             "**/CLAUDE.md"]
# refusals that a prefix rule misses: an option after other arguments (--amend, -n for
# --no-verify), git's --force and -f, and the read-only commands that can write a file
DENY_PATTERNS = ["Bash(* --no-verify*)", "Bash(* --amend*)", "Bash(git commit -n*)", "Bash(git commit * -n*)",
                 "Bash(git * --force*)", "Bash(git * -f)", "Bash(git * -f *)", "Bash(git * --output*)",
                 "Bash(sort -o*)", "Bash(sort * -o *)", "Bash(sort * -o*)", "Bash(sort *--output*)"]
# the verdict files have one author (CONTRACTS.md §6): the engine and the story-reviewer
VERIFICATION = "docs/stories/*/verification.md"
REVIEW = "docs/stories/*/review.md"
KIT_SCRIPTS = ["Bash(bash qualification/kit/*)", "Bash(sh qualification/kit/*)", "Bash(./qualification/kit/*)"]
PROMPTS = {
    "story-implementer": "Story {label} — read docs/stories/{id}/order.md and carry it out. Mode: {mode}.",
    "story-reviewer": "Story {label} — review the change at code tree {tree} against the target branch {target}. "
                      "Loop {loop}.",
    "technical-lead": "/run-campaign {campaign}",
    "qualification-runner": "Qualification {id}: carry out qualification/order.md.",
}


# the cloud session has no role settings and no --agent: the prompt names the agent file
CLOUD_PROMPT = ("You are the story-implementer of this repository: read .claude/agents/story-implementer.md "
                "and follow it as your instructions. " + PROMPTS["story-implementer"] +
                " Where: cloud — use port {port} wherever DELIVERY_PORT or {{port}} is asked.")


def plugin_root() -> Path | None:
    """Where the plugin lives: DELIVERY_PLUGIN_ROOT (set by the plugin launcher), then the
    machine setting plugin_dir, then the Claude Code plugin registry."""
    candidates = [os.environ.get("DELIVERY_PLUGIN_ROOT", ""), config.machine().get("plugin_dir", "")]
    for cand in candidates:
        path = Path(os.path.expanduser(cand)) if cand else None
        if path and (path / ".claude-plugin" / "plugin.json").exists():
            return path
    registry = Path(os.path.expanduser("~/.claude/plugins/installed_plugins.json"))
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    best = None
    for key, entries in (data.get("plugins") or {}).items():
        if not key.startswith(PLUGIN + "@"):
            continue
        for entry in entries:
            path = Path(entry.get("installPath", ""))
            if (path / ".claude-plugin" / "plugin.json").exists():
                if entry.get("version") == VERSION:
                    return path
                best = best or path
    return best


def _abs(path: Path, pattern: str = "") -> str:
    """Absolute path pattern for a permission rule: '//' + absolute path."""
    text = str(Path(path).resolve())
    return "/" + text + ("/" + pattern if pattern else "")


def _bash(prefixes) -> list[str]:
    out = []
    for prefix in prefixes:
        out.append(f"Bash({prefix})")
        out.append(f"Bash({prefix} *)")
    return out


def _command_rules(cfg: Config) -> list[str]:
    rules = []
    for name in ("check", "test", "acceptance", "serve"):
        template = cfg.commands.get(name)
        if template:
            rules += _bash([template.split("{", 1)[0].strip()])
    return rules


def _write(folder: Path, patterns) -> list[str]:
    out = []
    for pattern in patterns:
        out += [f"Edit({_abs(folder, pattern)})", f"Write({_abs(folder, pattern)})"]
    return out


def permissions(cfg: Config, role: str, worktree: Path, scope: str) -> dict:
    if role not in UNATTENDED:
        fail(EXIT_ERROR, f"'{role}' is not an unattended role")
    wt = Path(worktree)
    allow = ["Read", "Glob", "Grep", "TodoWrite", "Skill"]
    allow += _bash(READ_ONLY_SHELL + GIT_READ + ENGINE_READ + ["just --list"])
    allow += _command_rules(cfg)
    allow += [rule if "(" in rule else f"Bash({rule})" for rule in cfg.extra_allow]
    deny = list(DENY_TOOLS)
    deny += _bash(DENY_BASH)
    deny += DENY_PATTERNS
    deny += [f"Read({p})" for p in SECRET_READS + [f"**/{ARCHIVE}/**"]]
    deny += [f"Bash(*{ARCHIVE}*)"]
    deny += _write(wt, PROTECTED)
    extra = {}
    if role == "story-implementer":
        allow += _write(wt, ["**"]) + _bash(GIT_WRITE)
        deny += _write(wt, [VERIFICATION, REVIEW]) + _moves_onto(["verification.md", "review.md"])
    elif role == "story-reviewer":
        allow += _write(wt, ["**"]) + _bash(GIT_WRITE + ["git stash", "git stash pop"])
        deny += _write(wt, [VERIFICATION]) + _moves_onto(["verification.md"])
    elif role == "qualification-runner":
        allow += _write(wt, ["qualification/**", "backlog/**"])
        allow += _bash(GIT_WRITE + ["docker", "docker compose", "curl", "just", "mkdir"]) + KIT_SCRIPTS
    elif role == "technical-lead":
        main = Path(cfg.root)
        worktrees = worktree_path(main, "x").parent
        allow += _write(main, ["backlog/**", "docs/campaigns/**"])
        allow += _write(worktrees, ["*/docs/stories/*/order.md"])
        allow += _bash(GIT_WRITE + ["git fetch", "deliveryctl story prepare", "deliveryctl story open",
                                    "deliveryctl story wait", "deliveryctl story next",
                                    "deliveryctl story close", "deliveryctl campaign open"])
        # shell reads in the prepared worktrees (anchoring); writes stay limited to order.md
        extra["additionalDirectories"] = [str(worktrees)]
    env = {"DELIVERY_ROLE": role, "DELIVERY_STORY": scope}
    return {"permissions": {"allow": allow, "deny": deny, "defaultMode": "dontAsk", **extra}, "env": env}


def _moves_onto(names) -> list[str]:
    """`git mv` would write a file that Edit and Write may not."""
    return [f"Bash(git mv *{name}*)" for name in names]


def render(cfg: Config, role: str, worktree: Path, scope: str, extra_env: dict | None = None) -> Path:
    data = permissions(cfg, role, worktree, scope)
    data["env"].update(extra_env or {})
    path = run_dir(cfg.root) / "roles" / f"{scope}-{role}.json"
    write_json(path, data)
    return path


def launch(cfg: Config, role: str, worktree: Path, scope: str, prompt: str, headless: bool,
           extra_env: dict | None = None) -> dict:
    """Everything a window needs to start a role session: argv, env, cwd, session id, name."""
    if role not in ROLES:
        fail(EXIT_ERROR, f"unknown role '{role}'")
    if not (Path(worktree) / ".claude" / "agents" / f"{role}.md").exists():
        fail(EXIT_PRECONDITION, f".claude/agents/{role}.md not found in {worktree}: the project does not "
                                "carry the method's agents (commit them, or run 'deliveryctl init --upgrade')")
    settings = render(cfg, role, worktree, scope, extra_env)
    session_id = str(uuid.uuid4())
    name = f"{cfg.agent_prefix}-{scope}-{role}"
    argv = ["claude", "--agent", role, "--permission-mode", "dontAsk", "--setting-sources", "project",
            "--settings", str(settings), "--session-id", session_id, "--name", name]
    if headless:
        argv += ["-p", "--output-format", "stream-json", "--verbose"]
    argv.append(prompt)
    # the project's engine first, whether or not the SessionStart hook runs
    env = {"DELIVERY_ROLE": role, "DELIVERY_STORY": scope,
           "PATH": f"{Path(worktree) / '.delivery'}{os.pathsep}{os.environ.get('PATH', '')}"}
    env.update(extra_env or {})
    return {"argv": argv, "env": env, "cwd": str(worktree), "session_id": session_id,
            "name": name, "settings": str(settings)}


def cloud_launch(cfg: Config, worktree: Path, scope: str, prompt: str) -> dict:
    """What the cloud window needs to start the story-implementer as a Claude Code cloud
    session: model and effort from the agent file (a cloud session has no `--agent`), no
    settings file, no environment (the session gets the pushed repository only)."""
    agent = Path(worktree) / ".claude" / "agents" / "story-implementer.md"
    if not agent.exists():
        fail(EXIT_PRECONDITION, f".claude/agents/story-implementer.md not found in {worktree}: the project does "
                                "not carry the method's agents (commit them, or run 'deliveryctl init --upgrade')")
    head = fm.load(agent)[0]
    model, effort = str(head.get("model") or "sonnet"), str(head.get("effort") or "medium")
    return {"argv": ["claude", "--cloud", prompt, "--model", model, "--effort", effort],
            "env": {}, "cwd": str(worktree), "branch": f"story/{scope}", "name": f"{cfg.agent_prefix}-{scope}-story-implementer"}


def shell_line(spec: dict) -> str:
    env = " ".join(f"{k}={shlex.quote(v)}" for k, v in spec["env"].items())
    return f"cd {shlex.quote(spec['cwd'])} && {env} {shlex.join(spec['argv'])}"
