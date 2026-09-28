"""`deliveryctl verify <id>`: the engine runs the checks of a story and writes the verdict
(CONTRACTS.md §7). Raw output stays in work/ (throwaway); only the verdict is committed."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from pathlib import Path

from . import ports
from . import verdict as vd
from .config import Config
from .core import (EXIT_PRECONDITION, EXIT_RED, clean_env, fail, file_lock, glob_match, now_iso, read_json,
                   run_dir, write_json)
from .gitops import Git

COUNT_RX = [re.compile(r"(\d+) passed")]          # Playwright summary line
FAILED_RX = [re.compile(r"(\d+) failed")]
REGISTRY = "verdicts.json"


def story_dir(card_id: str) -> str:
    return f"docs/stories/{card_id}"


def doc_only(cfg: Config, changed: list[str], card_id: str) -> bool:
    own = story_dir(card_id) + "/"
    rest = [p for p in changed if not p.startswith(own)]
    return bool(rest) and all(glob_match(p, cfg.lever("doc_globs")) for p in rest)


def _count(output: str, patterns) -> int | None:
    found = None
    for rx in patterns:
        for match in rx.finditer(output):
            found = (found or 0) + int(match.group(1))
        if found is not None:
            return found
    return None


def run_step(command: str, cwd: Path, log: Path, timeout: int = 3600, env: dict | None = None,
             grace: int = 30) -> dict:
    """Run a command in its own process group, its output streamed to the log. On timeout the
    group gets SIGINT (a Ctrl-C lets test runners stop the servers they started), then SIGKILL
    after `grace` seconds; what a finished command leaves behind is stopped too."""
    log.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    with open(log, "ab") as fh:
        fh.write(f"$ {command}\n".encode())
        fh.flush()
        offset = fh.tell()
        proc = subprocess.Popen(command, shell=True, cwd=cwd, env=clean_env(env), stdin=subprocess.DEVNULL,
                                stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = proc.wait(timeout=timeout)
            _stop_group(proc, signal.SIGTERM, 2)
        except subprocess.TimeoutExpired:
            code = 124
            _stop_group(proc, signal.SIGINT, grace)
            fh.write(f"\ntimeout after {timeout}s\n".encode())
    seconds = int(time.monotonic() - start)
    with open(log, "rb") as fh:
        fh.seek(offset)
        output = fh.read().decode("utf-8", errors="replace")
    with open(log, "ab") as fh:
        fh.write(f"\n[exit {code}, {seconds}s]\n\n".encode())
    return {"command": command, "exit": code, "seconds": seconds,
            "tests": _count(output, COUNT_RX), "failed": _count(output, FAILED_RX)}


def _stop_group(proc: subprocess.Popen, first: int, grace: float) -> None:
    """Signal the process group, wait up to `grace` seconds for it to empty, then SIGKILL."""
    for sig, wait in ((first, grace), (signal.SIGKILL, 5)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            break
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            proc.poll()                  # reap the leader, or the group never looks empty
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                proc.wait()
                return
            time.sleep(0.1)
    proc.wait()


def plan_steps(cfg: Config, card, changed: list[str], port: int | str = "") -> tuple[list[tuple[str, str]], str]:
    """(steps, skip reason). A step is (kind, command) with kind 'check' or 'acceptance';
    {port} is the port of the story, {grep} the tag of its spec story."""
    subst = {"port": port} if port else {}
    check = cfg.command("check", **subst)
    if not check:
        fail(EXIT_PRECONDITION, "delivery.toml has no [commands] check")
    steps = [("check", check)]
    reason = ""
    if not cfg.command("acceptance"):
        reason = "no acceptance command"
    elif not card.spec:
        reason = "no spec story"
    elif not card.code:
        reason = "card without code"
    elif doc_only(cfg, changed, card.id):
        reason = "documentation only"
    else:
        steps.append(("acceptance", cfg.command("acceptance", grep=f"@{card.spec}", **subst)))
    return steps, reason


def verify(cfg: Config, worktree: Path, card_id: str, card, port: int | None = None) -> vd.Verdict:
    git = Git(worktree)
    port = port or ports.port(cfg, card_id)
    status = git.run("status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    tracked = [line[3:] for line in status if not line.startswith("??")]
    untracked = [line[3:] for line in status if line.startswith("??") and "/work/" not in line]
    if tracked:
        fail(EXIT_PRECONDITION, "uncommitted changes to tracked files in the story worktree:\n  "
             + "\n  ".join(tracked))
    base = git.merge_base("HEAD", git.target_ref())
    changed = git.diff_names(base)
    steps, skipped_reason = plan_steps(cfg, card, changed, port)
    tree = git.code_tree()
    log = worktree / story_dir(card_id) / "work" / "verify.log"
    results = []
    for kind, command in steps:
        res = run_step(command, worktree, log, env={"DELIVERY_PORT": str(port)})
        res["kind"] = kind
        results.append(res)
        if res["exit"] != 0:
            break
    ok = len(results) == len(steps) and all(r["exit"] == 0 for r in results)
    parts = []
    for r in results:
        if r["kind"] == "acceptance":
            count = r["tests"]
            if count is None or count == 0:
                if r["exit"] == 0:
                    ok = False
                parts.append(f"acceptance exit {r['exit']}, 0 tests")
            else:
                parts.append(f"acceptance exit {r['exit']}, {count} passed"
                             + (f", {r['failed']} failed" if r["failed"] else ""))
        else:
            parts.append(f"check exit {r['exit']}")
    for kind, command in steps[len(results):]:
        parts.append(f"{kind} not run (previous step failed)")
    if skipped_reason:
        parts.append(f"acceptance: not run — {skipped_reason}")
    seconds = sum(r["seconds"] for r in results)
    parts.append(f"{seconds // 60}m{seconds % 60:02d}s")
    result = "; ".join(parts)
    lines = [f"# Verification of {card_id}", "", f"- Date: {now_iso()}", f"- Base: {base}", ""]
    for r in results:
        lines.append(f"- `{r['command']}` → exit {r['exit']} in {r['seconds']}s")
    if untracked:
        shown = ", ".join(untracked[:8]) + (" …" if len(untracked) > 8 else "")
        lines.append(f"- Untracked files present during the run (not part of the verified tree): {shown}")
    lines.append("")
    commands = " && ".join(c for _, c in steps)
    block = vd.render("pass" if ok else "fail", tree, commands, result, "engine")
    path = worktree / story_dir(card_id) / "verification.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n" + block, encoding="utf-8")
    sha = git.commit([str(path.relative_to(worktree))], f"verify {card_id}: {'pass' if ok else 'fail'}",
                     [("Story", card_id), ("Agent", "engine")])
    register(cfg.root, card_id, "verification", sha)
    return vd.parse(path.read_text(encoding="utf-8"), "verification")


# -- engine registry of the verdicts it produced or asked for (CONTRACTS.md §6) ---------------
def registry(root: Path) -> dict | None:
    """What the engine recorded in <main>/.delivery/run, where no role writes: the sha of each
    verification commit it made, and the tree and head of each reviewer launch. None when the
    file does not exist (CI, fresh clone): then only the By: line and Agent: trailer count."""
    path = run_dir(root) / REGISTRY
    return read_json(path, {}) if path.exists() else None


def register(root: Path, card_id: str, kind: str, entry) -> None:
    runs = run_dir(root)
    with file_lock(runs / "verdicts.lock"):
        data = read_json(runs / REGISTRY, {})
        data.setdefault(card_id, {}).setdefault(kind, []).append(entry)
        write_json(runs / REGISTRY, data)


def unregister(root: Path, card_id: str) -> None:
    runs = run_dir(root)
    with file_lock(runs / "verdicts.lock"):
        data = read_json(runs / REGISTRY, {})
        if data.pop(card_id, None) is not None:
            write_json(runs / REGISTRY, data)


def history(git: Git, base: str, card_id: str, name: str, kind: str) -> list[vd.Verdict]:
    """Every committed version of a verdict file on the story branch, oldest first."""
    rel = f"{story_dir(card_id)}/{name}"
    commits = git.out("log", "--reverse", "--format=%H", f"{base}..HEAD", "--", rel).split()
    out = []
    for commit in commits:
        parsed = vd.parse(git.show(commit, rel), kind)
        if parsed:
            out.append(parsed)
    return out


def require_pass(result: vd.Verdict | None) -> None:
    if not result or not result.valid or result.verdict != "pass":
        fail(EXIT_RED, "verification is red")
