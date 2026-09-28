"""`deliveryctl nightly` (CONTRACTS.md §16): the full UI suite on the head of the target branch,
in a throwaway worktree. When it is red, a qualification-runner writes one anomaly card per
distinct fault; the engine commits them on anomalies/<date>, opens the merge request whose
review is the triage, and notifies. Never the full suite on every story."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path

from . import cards, journal, notify, ports, roles, window
from .config import Config
from .core import EXIT_OK, EXIT_PRECONDITION, EXIT_RED, EXIT_TOOL, DeliveryError, clean_env, fail, run_dir, today
from .forge import Forge
from .gitops import Git, worktree_path
from .verify import run_step
from .window.terminal import TerminalWindow

ROLE = "qualification-runner"
LOG = "qualification/work/nightly.log"
SUITE_TIMEOUT = 3 * 3600
RUNNER_TIMEOUT = 3600
PROMPT = (
    "Nightly run {day}: the full UI test suite is red at commit {short} of the target branch. "
    "The team triages your cards in the morning, so each card stands on its own. "
    "Scope: read {log} and the code; write only new cards in backlog/. "
    "Group the failing tests by cause and write one anomaly card per distinct fault, "
    "backlog/<id>-<slug>.md with ids from {next_id} upward: kind: anomaly, status: to-triage, "
    "found: nightly-{day}@{short}, spec: the spec story of the failing test tag (@s004 gives s004); "
    "sections Objective (the fault in one sentence), Context and scope (failing tests, observed "
    "and expected result, log lines), Oracle (the tests that pass once it is fixed). "
    "Do not fix the product and do not push. Run 'deliveryctl cards lint' until it reports "
    "nothing about your cards, then commit them with the trailers 'Campaign: nightly-{day}' and "
    "'Agent: qualification-runner'. End with an Outcome line."
)


def run(cfg: Config) -> int:
    day = today()
    scope = f"nightly-{day}"
    if not (cfg.command("acceptance") or "").strip():
        fail(EXIT_PRECONDITION, "delivery.toml has no [commands] acceptance")
    try:
        return _run(cfg, day, scope, ports.port(cfg, scope))
    finally:
        ports.release(cfg, scope)


def _run(cfg: Config, day: str, scope: str, port: int) -> int:
    branch = f"anomalies/{day}"
    command = (cfg.command("acceptance", grep="", port=port) or "").strip()
    main = Git(cfg.root)
    main.fetch()
    main.run("worktree", "prune", check=False)
    wt = worktree_path(cfg.root, scope)
    if main.rev(branch):
        left = main.worktree_for(branch)
        if main.out("rev-list", "--count", f"{main.target_ref()}..{branch}") != "0":
            remove = f"git worktree remove --force {left} && " if left else ""
            fail(EXIT_PRECONDITION, f"{branch} already exists with anomaly cards: triage it, or delete it "
                                    f"to run again ({remove}git branch -D {branch})")
        _drop(main, left or wt, branch)          # a leftover of an earlier run of the day
    head = main.rev(main.target_ref())
    wt.parent.mkdir(parents=True, exist_ok=True)
    main.worktree_add(wt, branch, head)
    res = run_step(command, wt, wt / LOG, timeout=SUITE_TIMEOUT, env={"DELIVERY_PORT": str(port)})
    log = _keep_log(cfg, wt / LOG, scope)
    short, tests = head[:7], res["tests"] or 0
    if res["exit"] == 0:
        _drop(main, wt, branch)
        if tests:
            journal.record(journal.event(cfg.root.name, "summary",
                                         f"nightly {day}: full UI suite green at {short}, {tests} passed",
                                         evidence=str(log)))
            print(f"nightly {day}: green at {short} ({tests} passed); log {log}")
            return EXIT_OK
        _alert(cfg, f"night:{day}:empty", "suite de nuit sans test", f"0 test exécuté ; journal : {log}",
               "other", f"nightly {day}: '{command}' ran 0 tests at {short}", str(log))
        print(f"nightly {day}: 0 tests ran, counted as red; log {log}")
        return EXIT_RED

    try:
        prompt = PROMPT.format(day=day, short=short, log=LOG, next_id=_next_anomaly(main))
        _run_runner(cfg, scope, roles.launch(cfg, ROLE, wt, scope, prompt, headless=True))
    except DeliveryError as exc:
        _drop(main, wt, branch)                  # nothing to triage; the log is kept
        _alert(cfg, f"night:{day}:runner", "suite de nuit rouge, runner non lancé", exc.message[:200],
               "night-anomalies", f"nightly {day}: suite red at {short}, runner not started: {exc.message}",
               str(log))
        raise
    git = Git(wt)
    _commit_new_cards(git, scope)
    added, remarks = _added_cards(git, head)
    remarks += [f"{p}: not committed, dropped with the worktree" for p in git.dirty()]
    if not added:
        _alert(cfg, f"night:{day}:no-card", "suite de nuit rouge sans carte", f"lire {log} ; copie gardée : {wt}",
               "night-anomalies", f"nightly {day}: suite red at {short}, the runner wrote no card", str(log))
        print(f"nightly {day}: red at {short}, no anomaly card written; log {log}; worktree kept: {wt}")
        return EXIT_RED
    body = _request_body(day, short, command, res, added, remarks, log)
    url, note = "", f"forge = none: local branch, merge it with git merge --no-ff {branch}"
    if cfg.forge != "none":
        try:
            url, note = Forge(cfg, git).open_branch(branch, f"Anomalies du {day}", body), ""
        except DeliveryError as exc:
            note = f"local branch, push failed: {exc.message.splitlines()[0]}"
    where = url or branch
    main.run("worktree", "remove", "--force", str(wt))
    ids = ", ".join(c.id for c in added)
    notify.notify(cfg.root, f"night:{day}", "night", "anomalies à trier", f"{len(added)} carte(s) : {where}")
    journal.record(journal.event(cfg.root.name, "night-anomalies",
                                 f"{len(added)} anomaly card(s) from the full UI suite at {short}: {ids}",
                                 evidence=where))
    print(f"nightly {day}: red at {short}; {len(added)} anomaly card(s) ({ids}) on {where}")
    if note:
        print(f"  {note}")
    for remark in remarks:
        print(f"  - {remark}")
    return EXIT_RED


def _run_runner(cfg: Config, scope: str, spec: dict) -> dict:
    """The runner session, synchronously: the fake window in tests, else a headless process."""
    if os.environ.get("DELIVERY_FAKE_WINDOW"):
        return window.get(cfg.root).start_role(scope, ROLE, spec)
    if not shutil.which(spec["argv"][0]):
        fail(EXIT_TOOL, f"the '{spec['argv'][0]}' command is not available")
    term = TerminalWindow(cfg.root)
    log = term.log_path(scope, ROLE)
    env = clean_env(spec["env"])
    with open(log, "ab") as out:
        proc = subprocess.Popen(spec["argv"], cwd=spec["cwd"], env=env, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    info = {"pid": proc.pid, "session_id": spec["session_id"], "log": str(log), "name": spec["name"],
            "cwd": spec["cwd"]}
    term.remember(scope, ROLE, info)
    try:
        info["exit"] = proc.wait(timeout=RUNNER_TIMEOUT)
    except subprocess.TimeoutExpired:
        info["exit"] = f"timeout after {RUNNER_TIMEOUT}s"
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
                proc.wait(timeout=30)
                break
            except ProcessLookupError:
                break
            except subprocess.TimeoutExpired:
                continue
    term.remember(scope, ROLE, info)
    return info


def _next_anomaly(git: Git) -> str:
    numbers = [int(c.id[1:]) for c in cards.load_from_rev(git, git.target_ref())
               if c.id[:1] == "a" and c.id[1:].isdigit()]
    return f"a{max(numbers, default=0) + 1:03d}"


def _commit_new_cards(git: Git, scope: str) -> None:
    """Commit the new cards the runner left uncommitted (the engine commits them, §16)."""
    new = [p for p in git.dirty() if p.startswith(cards.BACKLOG + "/") and p.endswith(".md")
           and not git.exists("HEAD", p)]
    if new:
        git.commit(new, f"anomaly cards of {scope}", [("Campaign", scope), ("Agent", "engine")])


def _added_cards(git: Git, base: str) -> tuple[list, list[str]]:
    added, remarks = [], []
    for status, path in git.diff_status(base, "HEAD"):
        if not (path.startswith(cards.BACKLOG + "/") and status == "A"):
            remarks.append(f"{path}: changed outside new backlog cards ({status})")
            continue
        card = cards.parse(Path(path), git.show("HEAD", path) or "")
        added.append(card)
        if card.kind != "anomaly" or card.status != "to-triage":
            remarks.append(f"{path}: not an anomaly to triage")
        elif not card.found:
            remarks.append(f"{path}: 'found:' is empty")
        remarks += [f"{path}: {p}" for p in card.problems]
    return added, remarks


def _request_body(day, short, command, res, added, remarks, log: Path) -> str:
    failed = f", {res['failed']} échec(s)" if res.get("failed") else ""
    lines = [f"# Anomalies du {day}", "",
             f"Suite complète des tests d'IHM rouge sur la branche cible à `{short}` : "
             f"`{command}` → exit {res['exit']}{failed}.", "",
             "Tri à la relecture de cette demande : corriger (maturation puis `ready`), reporter "
             "(`deferred`), abandonner (`dropped`), ou remonter une question de spec.", "", "## Cartes", ""]
    lines += [f"- `{c.rel}` — {c.title or c.id}" + (f" — spec {c.spec}" if c.spec else "") for c in added]
    if remarks:
        lines += ["", "## Points à vérifier", ""] + [f"- {r}" for r in remarks]
    tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:] if log.exists() else []
    lines += ["", "## Fin du journal de la suite", "", "```", *tail, "```", ""]
    return "\n".join(lines)


def _keep_log(cfg: Config, path: Path, scope: str) -> Path:
    kept = run_dir(cfg.root) / "logs" / f"{scope}.log"
    kept.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copyfile(path, kept)
    return kept


def _drop(main: Git, wt: Path, branch: str) -> None:
    if Path(wt).exists():
        main.run("worktree", "remove", "--force", str(wt), check=False)
    main.run("worktree", "prune", check=False)
    main.run("branch", "-D", branch, check=False)


def _alert(cfg: Config, key: str, subject: str, message: str, category: str, text: str,
           evidence: str) -> None:
    notify.notify(cfg.root, key, "decision", subject, message)
    journal.record(journal.event(cfg.root.name, category, text, evidence=evidence))
