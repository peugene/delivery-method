"""Shared plumbing: errors and exit codes, subprocess calls, paths, locks, glob matching."""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_RED = 2
EXIT_PRECONDITION = 3
EXIT_REFUSED = 4
EXIT_TOOL = 5

ID_RX = re.compile(r"^[sta][0-9]{3,4}$")
SLUG_RX = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
ROLES = (
    "product-analyst",
    "spec-reviewer",
    "refuter",
    "technical-lead",
    "story-implementer",
    "story-reviewer",
    "qualification-lead",
    "qualification-runner",
)


class DeliveryError(Exception):
    """An error that ends the command with a contract exit code (CONTRACTS.md §17)."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def fail(code: int, message: str) -> None:
    raise DeliveryError(code, message)


def eprint(*args) -> None:
    print(*args, file=sys.stderr)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def check_id(value: str) -> str:
    if not ID_RX.match(value or ""):
        fail(EXIT_ERROR, f"invalid card id '{value}' (expected s001, t012, a003…)")
    return value


def check_slug(value: str, what: str = "name") -> str:
    if not SLUG_RX.match(value or ""):
        fail(EXIT_ERROR, f"invalid {what} '{value}' (lowercase letters, digits and dashes)")
    return value


def run(cmd, cwd=None, check=True, env=None, timeout=None, input_text=None) -> subprocess.CompletedProcess:
    """Run a command (list or shell string) and capture text output."""
    shell = isinstance(cmd, str)
    full_env = None
    if env is not None:
        full_env = dict(os.environ)
        full_env.update(env)
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            shell=shell,
            env=full_env,
            text=True,
            capture_output=True,
            timeout=timeout,
            input=input_text,
        )
    except FileNotFoundError as exc:
        fail(EXIT_TOOL, f"tool not found: {exc.filename}")
    except subprocess.TimeoutExpired:
        fail(EXIT_TOOL, f"timeout after {timeout}s: {cmd if shell else ' '.join(cmd)}")
    if check and proc.returncode != 0:
        shown = cmd if shell else " ".join(cmd)
        detail = (proc.stderr or proc.stdout).strip()
        fail(EXIT_TOOL, f"command failed ({proc.returncode}): {shown}\n{detail}")
    return proc


PARENT_ENV_PREFIXES = ("HERDR_", "CLAUDE_CODE_", "DELIVERY_")
PARENT_ENV_KEYS = ("CLAUDECODE", "CLAUDE_EFFORT", "CLAUDE_PID")


def clean_env(extra: dict | None = None) -> dict:
    """Environment for a process started by the engine: without the identity of the session or
    pane that launched it (multiplexer pane, Claude session ids, messaging socket and token,
    delivery role), plus `extra`. User settings such as CLAUDE_CONFIG_DIR are kept."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(PARENT_ENV_PREFIXES) and k not in PARENT_ENV_KEYS}
    if os.environ.get("DELIVERY_PLUGIN_ROOT"):
        env["DELIVERY_PLUGIN_ROOT"] = os.environ["DELIVERY_PLUGIN_ROOT"]
    if os.environ.get("DELIVERY_WINDOW"):
        env["DELIVERY_WINDOW"] = os.environ["DELIVERY_WINDOW"]
    env.update(extra or {})
    return env


def is_role_session() -> bool:
    return bool(os.environ.get("DELIVERY_ROLE"))


def is_claude_session() -> bool:
    return bool(os.environ.get("CLAUDECODE")) or is_role_session()


def require_human(gesture: str) -> None:
    """Human gestures are refused inside role sessions (CONTRACTS.md §12.1)."""
    if is_role_session():
        fail(EXIT_REFUSED, f"'{gesture}' is a human gesture: refused in a role session "
                           f"(DELIVERY_ROLE={os.environ.get('DELIVERY_ROLE')})")


def is_cloud() -> bool:
    """True inside a Claude Code cloud session (CONTRACTS.md §2)."""
    return os.environ.get("CLAUDE_CODE_REMOTE") == "true"


# Verb (and sub-verb) of the gestures that run from the owner's computer only; `require_local` and
# the PreToolUse hook read this one list.
CLOUD_REFUSED = ("run", "merge", "submit", "story open", "story next", "story wait", "qualify run",
                 "qualify submit", "nightly", "spec release", "init", "note", "journal report")


def cloud_refusal(gesture: str) -> str:
    return f"'deliveryctl {gesture}' ne tourne pas dans une session cloud : lancez-la depuis votre ordinateur"


def require_local(gesture: str) -> None:
    """Gestures that start Claude sessions, push, tag or merge on the forge, or write the owner's
    journal run from the owner's computer (CONTRACTS.md §12.1)."""
    assert gesture in CLOUD_REFUSED, gesture
    if is_cloud():
        fail(EXIT_REFUSED, cloud_refusal(gesture))


def repo_root(start: Path | None = None) -> Path:
    """Top level of the current checkout (a story worktree or the main checkout)."""
    proc = run(["git", "rev-parse", "--show-toplevel"], cwd=start or Path.cwd(), check=False)
    if proc.returncode != 0:
        fail(EXIT_PRECONDITION, "not inside a git repository")
    return Path(proc.stdout.strip())


def main_root(start: Path | None = None) -> Path:
    """Main checkout of the repository, shared by all story worktrees."""
    proc = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
               cwd=start or Path.cwd(), check=False)
    if proc.returncode != 0:
        fail(EXIT_PRECONDITION, "not inside a git repository")
    common = Path(proc.stdout.strip())
    return common.parent if common.name == ".git" else common


def run_dir(root: Path) -> Path:
    """Engine runtime state, ignored by git; roles never write here."""
    path = main_root(root) / ".delivery" / "run"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_home() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    path = Path(base) / "delivery-method"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_home() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "delivery-method"


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


@contextmanager
def file_lock(path: Path, blocking: bool = True):
    """Advisory lock; with blocking=False, yields False when another process holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def glob_to_regex(pattern: str) -> re.Pattern:
    """Git-style glob: '**' spans directories, '*' and '?' stay inside one segment.
    A pattern without '/' matches a basename anywhere."""
    if "/" not in pattern.rstrip("/"):
        pattern = "**/" + pattern
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif ch == "*":
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    body = "".join(out)
    if pattern.endswith("/"):
        body += ".*"
    return re.compile("^" + body + "$")


def glob_match(path: str, patterns) -> bool:
    return any(glob_to_regex(p).match(path) for p in patterns)
