"""Story life cycle (CONTRACTS.md §6, §9, §12): prepare, open, state, next, wait, submit, merge,
close. Every state is derived from the committed story files and the forge, never from a
window or a memory."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import VERSION, cards, frontmatter as fm, gate, journal, notify, ports, roles, window
from . import verdict as vd
from .config import Config
from .core import (EXIT_PRECONDITION, EXIT_RED, EXIT_REFUSED, EXIT_TOOL, DeliveryError, check_id, clean_env,
                   eprint, fail, file_lock, read_json, require_human, run_dir, write_json)
from .forge import Forge, request_body
from .gitops import Git, story_branch, worktree_path
from .verify import register, registry, story_dir, unregister, verify

STATE_WORDS = {"blocked": "bloquée", "deferred": "différée", "plan-ready": "plan à relire"}
STOPPED = ("blocked", "deferred", "plan-ready", "verify-exhausted", "review-exhausted")
TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
ORDER_SECTIONS = ("Objective", "Decisions", "Proposal", "Constraints",
                  "Read at base — re-verify, do not trust", "Reinforced checks", "Deliverables")


@dataclass
class State:
    id: str
    name: str
    title: str = ""
    worktree: Path | None = None
    tree: str = ""
    outcome: tuple | None = None
    fresh: bool = False
    fix_mode: str = ""
    verify_fails: int = 0
    review_noes: int = 0
    detail: str = ""
    engine_next: str = ""
    human_next: str = ""
    extra: dict = field(default_factory=dict)


# -- timeline of the story branch -----------------------------------------------------------
def _timeline(git: Git, base: str, card_id: str, reg: dict | None = None) -> dict:
    """Walk the branch commits oldest first and record, for the story files, the index of the
    last commit touching each and the verdicts written. A verdict counts only when written by
    its author (By: line and Agent: trailer, CONTRACTS.md §6) and, when the engine registry
    exists (`reg`), when the engine made that verification or launched a reviewer on that tree.
    A review.md commit without a valid verdict block counts against review_loops."""
    own = story_dir(card_id) + "/"
    commits = git.out("rev-list", "--reverse", f"{base}..HEAD").split()
    authors = gate.agents(git, base)
    t = {"commits": commits, "report": None, "ver": None, "rev": None, "neg": None, "neg_kind": "",
         "fails": 0, "noes": 0, "ver_verdict": None, "rev_verdict": None}
    for idx, commit in enumerate(commits):
        names = git.out("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit).split("\n")
        agent = authors.get(commit, "")
        if own + "report.md" in names:
            t["report"] = idx
        if own + "verification.md" in names and agent == vd.AUTHORS["verification"] and (
                reg is None or commit in reg.get("verification", [])):
            parsed = vd.parse(git.show(commit, own + "verification.md"), "verification")
            if parsed and parsed.valid:
                t["ver"], t["ver_verdict"] = idx, parsed
                if parsed.verdict == "fail":
                    t["fails"] += 1
                    t["neg"], t["neg_kind"] = idx, "verification"
        tree = git.code_tree(commit) if own + "review.md" in names else ""
        if tree and (reg is None or _reviewer_launched(git, commit, tree, reg)):
            parsed = vd.parse(git.show(commit, own + "review.md"), "review")
            if parsed and agent != vd.AUTHORS["review"]:
                parsed.problems.append(f"committed with 'Agent: {agent or 'none'}'")
            if parsed and parsed.tree and parsed.tree != tree:
                parsed.problems.append("Tree is not the code tree of the reviewed commit")
            t["rev"], t["rev_verdict"] = idx, parsed
            if not parsed or not parsed.valid or parsed.verdict == "no":
                t["noes"] += 1
            if parsed and parsed.valid and parsed.verdict == "no":
                t["neg"], t["neg_kind"] = idx, "review"
    return t


def _reviewer_launched(git: Git, commit: str, tree: str, reg: dict) -> bool:
    """The engine launched a story-reviewer on this code tree, before this commit."""
    return any(item.get("tree") == tree and item.get("head") != commit
               and git.is_ancestor(item.get("head", ""), commit) for item in reg.get("review", []))


def _card(git: Git, card_id: str, cfg: Config | None = None) -> cards.Card:
    risks = cfg.risks if cfg else cards.RISKS
    return cards.find(cards.load_from_rev(git, git.target_ref(), risks), card_id)


def label(st: State) -> str:
    return cards.label(st.id, st.title)


def _labels(cfg: Config, ids) -> str:
    return cards.labels(ids, cards.titles(Git(cfg.root)))


# -- state ----------------------------------------------------------------------------------
def state(cfg: Config, card_id: str) -> State:
    check_id(card_id)
    main = Git(cfg.root)
    branch = story_branch(card_id)
    wt = main.worktree_for(branch)
    st = State(id=card_id, name="none", worktree=wt, title=cards.titles(main).get(card_id, ""))
    if card_id in cards.merged_ids(main):
        st.name = "merged" if wt else "closed"
        st.engine_next = "close the worktree" if wt else ""
        return st
    if not wt:
        st.detail = "no worktree"
        return st
    git = Git(wt)
    base = git.merge_base("HEAD", git.target_ref())
    own = story_dir(card_id) + "/"
    reg = registry(cfg.root)
    t = _timeline(git, base, card_id, None if reg is None else reg.get(card_id, {}))
    if not t["commits"]:
        st.name = "prepared"
        st.human_next = f"write {own}order.md, then: deliveryctl story open {card_id}"
        return st
    st.tree = git.code_tree()
    st.verify_fails, st.review_noes = t["fails"], t["noes"]
    st.outcome = vd.outcome(git.show("HEAD", own + "report.md"))
    report_idx = t["report"]
    if st.outcome and report_idx is not None and (t["neg"] is None or report_idx > t["neg"]):
        st.fresh = git.code_tree(t["commits"][report_idx]) == st.tree
    rev, ver = t["rev_verdict"], t["ver_verdict"]
    # submitted / ready-to-submit: a valid 'yes' on the current tree, after the last report
    if (rev and rev.valid and rev.verdict == "yes" and rev.tree == st.tree
            and (report_idx is None or t["rev"] > report_idx)):
        return _submission(cfg, main, git, st)
    if st.fresh and st.outcome[0] in ("blocked", "deferred", "plan-ready", "question"):
        st.name = "blocked" if st.outcome[0] == "question" else st.outcome[0]
        st.detail = st.outcome[1]
        st.human_next = {"plan-ready": f"read {own}plan.md, then: deliveryctl story next {card_id} --go",
                         "deferred": f"read {own}report.md and {own}spec-question.md"}.get(
            st.outcome[0], f"read {own}report.md")
        return st
    last = max((i for i in (t["ver"], t["rev"]) if i is not None), default=None)
    if not st.fresh and t["neg"] is not None and t["neg"] == last:
        if t["neg_kind"] == "verification":
            if t["fails"] > cfg.lever("verify_attempts"):
                st.name = "verify-exhausted"
                st.human_next = f"read {own}verification.md and {own}work/verify.log"
                return st
            st.fix_mode = "fix-verification"
        else:
            if t["noes"] > cfg.lever("review_loops"):
                st.name = "review-exhausted"
                st.human_next = f"read {own}review.md"
                return st
            st.fix_mode = "fix-review"
        st.name = "fixing"
        st.engine_next = f"start story-implementer ({st.fix_mode})"
        st.extra["step"] = t["commits"][t["neg"]]
        return st
    if not st.fresh:
        st.name = "open" if len(t["commits"]) == 1 else "implementing"
        st.engine_next = "start story-implementer"
        st.extra["step"] = t["commits"][0] if st.name == "open" else ""
        return st
    if ver is None or t["ver"] < report_idx or ver.tree != st.tree:
        st.name = "to-verify"
        st.engine_next = f"deliveryctl verify {card_id}"
        return st
    # to review; a review after this verification without a valid verdict counts against
    # review_loops, and so does every reviewer launched on this tree that wrote nothing new
    invalid = t["rev"] is not None and t["rev"] > t["ver"] and not (rev and rev.valid and rev.tree != st.tree)
    launched = sum(1 for item in (reg or {}).get(card_id, {}).get("review", []) if item.get("tree") == st.tree)
    if invalid:
        st.detail = f"{own}review.md has no valid verdict: " + ("; ".join(rev.problems) if rev
                                                                 else "no verdict block")
    if (invalid and t["noes"] > cfg.lever("review_loops")) or launched > cfg.lever("review_loops"):
        st.name = "review-exhausted"
        st.detail = st.detail or f"{launched} reviewers launched on this code tree, no verdict"
        st.human_next = f"read {own}review.md"
        return st
    st.name = "to-review"
    st.engine_next = "start a fresh story-reviewer"
    return st


def _submission(cfg: Config, main: Git, git: Git, st: State) -> State:
    """A valid 'yes' on the current tree: merged, submitted or ready-to-submit, from the forge.
    The forge is asked even when the remote branch is gone (deleted at the merge); a request
    counts as submitted only when the pushed head is the local head."""
    card_id, branch = st.id, story_branch(st.id)
    try:
        proc = main.run("ls-remote", "origin", f"refs/heads/{branch}", check=False, timeout=60)
        if proc.returncode != 0:
            fail(EXIT_TOOL, (proc.stderr or proc.stdout).strip() or "git ls-remote origin failed")
        remote = proc.stdout.split()
        mr = Forge(cfg, git).find(card_id)
    except DeliveryError as exc:
        st.name = "ready-to-submit"
        st.detail = f"forge unreachable: retry ({exc.message.splitlines()[0][:160]})"
        return st
    if mr and mr["state"] == "merged":
        st.name = "merged"
        st.engine_next = "close the worktree"
        return st
    pushed = bool(remote) and remote[0] == git.head()
    st.name = "submitted" if pushed and mr and mr["state"] in ("open", "opened") else "ready-to-submit"
    st.extra["mr"] = mr
    if st.name == "ready-to-submit":
        st.engine_next = f"deliveryctl submit {card_id}"
    elif cfg.integration == "ai":
        st.engine_next = f"deliveryctl merge {card_id} when the CI is green"
    else:
        st.human_next = f"review and merge the merge request of {branch}"
    return st


# -- prepare and open -----------------------------------------------------------------------
def prepare(cfg: Config, card_id: str) -> Path:
    """Worktree from the head of the target branch and an order skeleton for the lead."""
    check_id(card_id)
    main = Git(cfg.root)
    main.fetch()
    card = _card(main, card_id, cfg)
    if card.status != "ready":
        fail(EXIT_PRECONDITION, f"{cards.label(card_id, card.title)} is '{card.status}': "
                                "only a ready card can be prepared")
    branch = story_branch(card_id)
    wt = main.worktree_for(branch)
    if not wt:
        wt = worktree_path(cfg.root, card_id)
        wt.parent.mkdir(parents=True, exist_ok=True)
        main.worktree_add(wt, branch, main.target_ref())
    order = wt / story_dir(card_id) / "order.md"
    if not order.exists():
        order.parent.mkdir(parents=True, exist_ok=True)
        text = (TEMPLATES / "story" / "order.md").read_text(encoding="utf-8")
        text = text.replace("<id>", card_id).replace("<base>", Git(wt).head())
        if os.environ.get("DELIVERY_CAMPAIGN"):
            text = text.replace("<campaign>", os.environ["DELIVERY_CAMPAIGN"])
        order.write_text(text, encoding="utf-8")
    (wt / story_dir(card_id) / "work").mkdir(parents=True, exist_ok=True)
    return order


def order_problems(text: str) -> list[str]:
    try:
        data, body = fm.split(text, "order.md")
    except fm.FrontmatterError as exc:
        return [exc.message]
    problems = []
    for section in ORDER_SECTIONS:
        content = fm.section_get(body, section)
        if content is None:
            problems.append(f"missing section '## {section}'")
        elif section in ("Objective", "Deliverables") and not fm.meaningful(content):
            problems.append(f"section '## {section}' is empty")
    for key in ("campaign", "base"):
        if not data.get(key) or str(data.get(key)).startswith("<"):
            problems.append(f"frontmatter '{key}' is not filled")
    if data.get("path", "plan") not in ("plan", "short"):
        problems.append("frontmatter 'path' must be plan or short")
    return problems


def _in_flight(cfg: Config, other_than: str) -> list[str]:
    out = []
    for cid in open_ids(cfg):
        if cid == other_than:
            continue
        st = state(cfg, cid)
        if st.name not in STOPPED + ("prepared", "merged", "closed", "none"):
            out.append(label(st))
    return out


def open_story(cfg: Config, card_id: str, order_draft: Path | None = None, start: bool = True) -> State:
    """Commit the order as the only file of the first commit and start the implementer."""
    check_id(card_id)
    main = Git(cfg.root)
    done = cards.merged_ids(main)
    card = _card(main, card_id, cfg)
    name = cards.label(card_id, card.title)
    if card.status != "ready":
        fail(EXIT_PRECONDITION, f"{name} is '{card.status}': only a ready card can be opened")
    missing = [d for d in card.depends_on if d not in done]
    if missing:
        fail(EXIT_PRECONDITION, f"{name} depends on cards not done yet: {_labels(cfg, missing)}")
    flying = _in_flight(cfg, card_id)
    if len(flying) >= cfg.max_in_flight:
        fail(EXIT_PRECONDITION, f"max_in_flight = {cfg.max_in_flight}; in flight: {'; '.join(flying)}")
    wt = main.worktree_for(story_branch(card_id))
    if not wt:
        prepare(cfg, card_id)
        wt = main.worktree_for(story_branch(card_id))
    git = Git(wt)
    if git.first_commit_files(git.merge_base("HEAD", git.target_ref())):
        fail(EXIT_PRECONDITION, f"{name} is already open")
    rel = f"{story_dir(card_id)}/order.md"
    order = wt / rel
    if order_draft:
        order.parent.mkdir(parents=True, exist_ok=True)
        order.write_text(Path(order_draft).read_text(encoding="utf-8"), encoding="utf-8")
    text = order.read_text(encoding="utf-8")
    problems = order_problems(text)
    if problems:
        fail(EXIT_RED, "order.md is not complete:\n  " + "\n  ".join(problems))
    base = str(fm.split(text)[0].get("base"))
    if not git.rev(base):
        fail(EXIT_RED, f"order.md: base '{base}' is not a commit of this repository")
    stale = [d for d in card.depends_on if d not in cards.merged_ids(git, base)]
    if stale:
        fail(EXIT_PRECONDITION, f"order.md was anchored before {_labels(cfg, stale)} was merged: "
                                "re-anchor at the head of the target branch and update 'base'")
    lines = len(text.splitlines())
    if lines > cfg.lever("max_order_lines"):
        eprint(f"note: order.md has {lines} lines (max_order_lines = {cfg.lever('max_order_lines')})")
    main.fetch()
    head = git.rev(git.target_ref())
    if git.head() != head:
        git.run("reset", "--quiet", "--keep", head)
    order_sha = git.commit([rel], f"order {name}", [("Story", card_id), ("Agent", "engine")])
    register(cfg.root, card_id, "order", order_sha)
    (wt / story_dir(card_id) / "work").mkdir(parents=True, exist_ok=True)
    ports.port(cfg, card_id)
    notify.forget(cfg.root, f"{card_id}:")
    window.get(cfg.root).open_story(card_id, wt)
    return next_step(cfg, card_id) if start else state(cfg, card_id)


# -- chaining -------------------------------------------------------------------------------
def _start(cfg: Config, card_id: str, role: str, prompt: str, step: str = "") -> dict:
    wt = Git(cfg.root).worktree_for(story_branch(card_id))
    win = window.get(cfg.root)
    spec = roles.launch(cfg, role, wt, card_id, prompt, headless=win.headless,
                        extra_env={"DELIVERY_PORT": str(ports.port(cfg, card_id))})
    info = win.start_role(card_id, role, spec)
    if step:
        reg = win.sessions(card_id)
        if role in reg:
            reg[role]["step"] = step
            write_json(run_dir(cfg.root) / "sessions" / f"{card_id}.json", reg)
    win.show_state(card_id, role)
    return info


def _start_implementer(cfg: Config, st: State, mode: str) -> None:
    """Start the implementer; a relaunch after a session of the same step that ended without
    an Outcome (a crash, a kill, a lost turn) is a resume, carried to the journal (§13)."""
    step = f"{mode}@{st.extra.get('step', '')}"
    prev = window.get(cfg.root).session(st.id, "story-implementer")
    if prev and (mode == "resume" or prev.get("step") == step):
        evidence = prev.get("log") or str(transcript_path(prev.get("cwd", ""), prev.get("session_id", "")))
        journal.record(journal.event(
            cfg.root.name, "resume", f"{label(st)} — story-implementer relaunched ({mode}); previous session "
            f"{prev.get('session_id', '?')} ended without an Outcome", story=st.id, role="story-implementer",
            evidence=evidence))
    _start(cfg, st.id, "story-implementer",
           roles.PROMPTS["story-implementer"].format(id=st.id, label=label(st), mode=mode), step)


def _alive(cfg: Config, card_id: str) -> list[str]:
    win = window.get(cfg.root)
    alive = []
    for role, info in win.sessions(card_id).items():
        if win.role_alive(card_id, role) is not False:     # unknown counts as alive (§9.1)
            alive.append(role)
        else:
            _record_denials(cfg, win, card_id, role, info)
    return alive


def _record_denials(cfg: Config, win, card_id: str, role: str, info: dict) -> None:
    """Carry the permission refusals of an ended headless session to the journal, once."""
    log = Path(info.get("log") or "")
    if info.get("denials_recorded") or not log.is_file():
        return
    denials = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if '"permission_denials"' not in line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        for item in data.get("permission_denials") or []:
            tool_input = item.get("tool_input") or {}
            what = tool_input.get("command") or tool_input.get("file_path") or ""
            denials.append(f"{item.get('tool_name')}: {str(what)[:160]}")
    info["denials_recorded"] = True
    info["denials"] = len(denials)
    reg = win.sessions(card_id)
    reg[role] = info
    write_json(run_dir(cfg.root) / "sessions" / f"{card_id}.json", reg)
    if denials:
        journal.record(journal.event(cfg.root.name, "refusal", f"{role}: " + " | ".join(denials[:10]),
                                     story=card_id, role=role, evidence=str(log)))


def _role_done(role: str, st: State) -> bool:
    if role == "story-implementer":
        return st.name not in ("open", "implementing", "fixing")
    if role == "story-reviewer":
        return st.name != "to-review"
    return False


def _finish_idle(cfg: Config, card_id: str, alive: list[str], st: State) -> list[str]:
    """An interactive role session stays open after its last turn: close the idle ones whose
    deliverable is written, so that the next role can start."""
    from .window.base import claude_sessions
    win = window.get(cfg.root)
    if win.headless:                     # a headless session ends with its turn
        return alive
    sessions = claude_sessions() or {}
    for role in alive:
        sid = (win.session(card_id, role) or {}).get("session_id")
        idle = (sessions.get(sid) or {}).get("status") == "idle"
        if idle and _role_done(role, st):
            win.stop_role(card_id, role)
    return _alive(cfg, card_id)


def next_step(cfg: Config, card_id: str, go: bool = False) -> State:
    """Do what the state calls for (CONTRACTS.md §9). Idempotent: nothing happens while a
    role session of the story is alive and working, or while another process advances it."""
    with file_lock(run_dir(cfg.root) / "locks" / f"{card_id}.lock", blocking=False) as got:
        return _advance(cfg, card_id, go) if got else state(cfg, card_id)


def _advance(cfg: Config, card_id: str, go: bool = False, chained: bool = False) -> State:
    """The body of next_step, under the story lock (not re-entrant: the steps that chain on,
    after verify and after a merge, call this again with chained=True, which runs neither
    verify nor merge a second time)."""
    st = state(cfg, card_id)
    alive = _alive(cfg, card_id)
    if alive:
        alive = _finish_idle(cfg, card_id, alive, st)
    if alive:
        st.detail = f"session running: {', '.join(alive)}"
        return st
    if st.name == "ready-to-submit" and st.engine_next:
        try:
            submit(cfg, card_id)
        except DeliveryError as exc:
            if exc.code != EXIT_RED:
                raise
            notify.notify(cfg.root, f"{card_id}:gate-red:{st.tree}", "decision",
                          notify.subject(card_id, st.title, "contrôle d'intégration rouge"), exc.message[:200])
            st.detail = exc.message
            return st
        st = state(cfg, card_id)
    if st.name in ("open", "implementing"):
        card = _card(Git(cfg.root), card_id, cfg)
        mode = "implement" if st.name == "open" else "resume"
        if card.show_plan and not (st.worktree / story_dir(card_id) / "plan.md").exists():
            mode = "plan-first"
        _start_implementer(cfg, st, mode)
    elif st.name == "fixing":
        _start_implementer(cfg, st, st.fix_mode)
    elif st.name == "plan-ready" and go:
        require_human("deliveryctl story next --go")
        _start_implementer(cfg, st, "implement-approved-plan")
    elif st.name == "to-verify" and not chained:
        card = _card(Git(cfg.root), card_id, cfg)
        try:
            verify(cfg, st.worktree, card_id, card)
        except DeliveryError as exc:
            notify.notify(cfg.root, f"{card_id}:verify-error:{st.tree}", "decision",
                          notify.subject(card_id, st.title, "vérification impossible"), exc.message[:200])
            st.detail = f"verification could not run: {exc.message}"
            return st
        return _advance(cfg, card_id, chained=True)
    elif st.name == "to-review":
        register(cfg.root, card_id, "review", {"tree": st.tree, "head": Git(st.worktree).head()})
        _start(cfg, card_id, "story-reviewer", roles.PROMPTS["story-reviewer"].format(
            id=card_id, label=label(st), tree=st.tree, target=Git(cfg.root).target_ref(), loop=st.review_noes + 1))
    elif st.name == "submitted":
        if cfg.integration == "ai":
            if chained:
                return st
            try:
                merge(cfg, card_id, by="story-reviewer")
                return _advance(cfg, card_id, chained=True)
            except Exception as exc:
                if getattr(exc, "code", None) == EXIT_RED:
                    notify.notify(cfg.root, f"{card_id}:merge-red:{st.tree}", "decision",
                                  notify.subject(card_id, st.title, "CI rouge"), str(exc)[:200])
                elif (st.extra.get("mr") or {}).get("checks") == "none":
                    _ci_absent(cfg, card_id, st)
                return state(cfg, card_id)
        notify.notify(cfg.root, f"{card_id}:submitted:{st.tree}", "decision",
                      notify.subject(card_id, st.title, "demande de fusion à relire"), st.human_next)
    elif st.name in ("blocked", "deferred", "plan-ready"):
        notify.notify(cfg.root, f"{card_id}:{st.name}:{st.tree}", "decision",
                      notify.subject(card_id, st.title, STATE_WORDS.get(st.name, st.name)), st.detail[:200] or st.human_next)
    elif st.name in ("verify-exhausted", "review-exhausted"):
        if notify.notify(cfg.root, f"{card_id}:{st.name}", "decision",
                         notify.subject(card_id, st.title, "borne atteinte"), st.human_next):
            journal.record(journal.event(cfg.root.name, st.name, f"{label(st)} — {st.human_next}", story=card_id))
    elif st.name == "merged" and cfg.integration == "ai":
        close(cfg, card_id)
    return state(cfg, card_id)


def _ci_absent(cfg: Config, card_id: str, st: State) -> None:
    """A merge request whose CI has not started after stall_minutes: one warning per tree."""
    path = run_dir(cfg.root) / "ci-waits.json"
    waits = read_json(path, {})
    key = f"{card_id}:{st.tree}"
    first = waits.setdefault(key, time.time())
    write_json(path, waits)
    if time.time() - first > cfg.lever("stall_minutes") * 60:
        notify.notify(cfg.root, f"{card_id}:ci-absent:{st.tree}", "decision",
                      notify.subject(card_id, st.title, "CI absente"),
                      f"aucun contrôle de CI sur la demande de fusion depuis {cfg.lever('stall_minutes')} min")


# -- submit, merge, close -------------------------------------------------------------------
def submit(cfg: Config, card_id: str) -> str:
    main = Git(cfg.root)
    wt = main.worktree_for(story_branch(card_id))
    if not wt:
        fail(EXIT_PRECONDITION, f"no worktree for {cards.label_of(main, card_id)}")
    git = Git(wt)
    problems = gate.check(git, card_id)
    if problems:
        fail(EXIT_RED, "integration check is red:\n  " + "\n  ".join(problems))
    card = _card(main, card_id, cfg)
    own = story_dir(card_id) + "/"
    body = request_body(card_id, card.title, git.show("HEAD", own + "report.md"),
                        git.show("HEAD", own + "verification.md"), git.show("HEAD", own + "review.md"), [])
    return Forge(cfg, git).open(card_id, request_title(card_id, card.title), body)


def request_title(card_id: str, title: str) -> str:
    """'<id> : <title> (story/<id>)': the suffix names the branch of a squash merge (§5)."""
    return f"{cards.label(card_id, title)} ({story_branch(card_id)})"


def merge_subject(card_id: str, title: str) -> str:
    """'Merge story/<id> : <title>': a subject naming story/<id> marks the card done (§5)."""
    return f"Merge {cards.label(story_branch(card_id), title)}"


def spec_ref(cfg: Config, card: cards.Card) -> str:
    if not card.spec:
        return "none"
    git = Git(cfg.root)
    lock = cfg.root / "spec.lock"
    version = "unversioned"
    if lock.exists():
        import tomllib
        version = tomllib.loads(lock.read_text(encoding="utf-8")).get("version", version)
    for path in git.run("ls-files", "spec/stories", check=False).stdout.split():
        if Path(path).name.startswith(card.spec + "-"):
            blob = git.blob("HEAD", path) or ""
            return f"{card.spec}@{version}#{blob[:7]}"
    return f"{card.spec}@{version}"


def _owner_email(git: Git) -> str:
    ident = git.out("var", "GIT_COMMITTER_IDENT", check=False)
    if "<" in ident and ">" in ident:
        return ident.split("<", 1)[1].split(">", 1)[0]
    return "decision-owner"


def merge(cfg: Config, card_id: str, by: str = "") -> str:
    if not by:
        require_human("deliveryctl merge")
    elif cfg.integration != "ai":
        fail(EXIT_REFUSED, "integration = human: only the decision owner merges")
    main = Git(cfg.root)
    wt = main.worktree_for(story_branch(card_id))
    if not wt:
        fail(EXIT_PRECONDITION, f"no worktree for {cards.label_of(main, card_id)}")
    git = Git(wt)
    problems = gate.check(git, card_id)
    if problems:
        fail(EXIT_RED, "integration check is red:\n  " + "\n  ".join(problems))
    card = _card(main, card_id, cfg)
    trailers = [("Story", card_id), ("Spec", spec_ref(cfg, card)),
                ("Approved-By", by or _owner_email(main)), ("Delivery-Method", VERSION)]
    summary = Forge(cfg, git).merge(card_id, merge_subject(card_id, card.title), trailers, head=git.head())
    from . import config as config_mod
    if config_mod.machine().get("notify_story_end"):
        notify.notify(cfg.root, f"{card_id}:merged", "story-end", notify.subject(card_id, card.title, "fusionnée"),
                      summary)
    return summary


def close(cfg: Config, card_id: str) -> str:
    """Remove the worktree of a merged story (and its branch), or of a stopped story (branch
    kept; human gesture)."""
    main = Git(cfg.root)
    wt = main.worktree_for(story_branch(card_id))
    merged = card_id in cards.merged_ids(main)
    if not merged:
        main.fetch()
        merged = card_id in cards.merged_ids(main)
    if not merged:
        st = state(cfg, card_id)
        if st.name not in STOPPED:
            fail(EXIT_PRECONDITION, f"{label(st)} is '{st.name}': only a merged or stopped story is closed")
        require_human("deliveryctl story close (stopped story)")
    kept = []
    if wt:
        work = wt / story_dir(card_id) / "work"
        if work.is_dir():
            kept = [str(p.relative_to(wt)) for p in work.rglob("*") if p.is_file()]
        window.get(cfg.root).close_story(card_id)
        main.run("worktree", "remove", "--force", str(wt))
    if merged:
        main.run("branch", "-D", story_branch(card_id), check=False)
    ports.release(cfg, card_id)
    unregister(cfg.root, card_id)
    note = f"closed {cards.label_of(main, card_id)}" + ("" if merged else " (branch kept)")
    if kept:
        note += f"; work files removed: {', '.join(kept[:10])}"
    return note


# -- waiting and watching -------------------------------------------------------------------
def transcript_path(cwd: str, session_id: str) -> Path:
    """Transcript of a Claude session: its project folder is the cwd with every character
    outside [A-Za-z0-9] replaced by '-'; a long path is shortened by Claude Code, so the
    session id (unique) is looked for in every project folder when the guess is absent."""
    base = Path(os.path.expanduser("~/.claude/projects"))
    guess = base / re.sub(r"[^A-Za-z0-9]", "-", cwd) / f"{session_id}.jsonl"
    if guess.exists() or not session_id:
        return guess
    return next(base.glob(f"*/{session_id}.jsonl"), guess)


def _progress(git: Git, wt: Path, card_id: str, info: dict) -> float:
    stamps = [float(git.commit_time())]
    folder = wt / story_dir(card_id)
    if folder.is_dir():
        stamps += [p.stat().st_mtime for p in folder.rglob("*") if p.is_file()]
    candidates = [transcript_path(info.get("cwd", ""), info.get("session_id", ""))]
    if info.get("log"):
        candidates.append(Path(info["log"]))
    stamps += [c.stat().st_mtime for c in candidates if c.exists()]
    return max(stamps)


def check_stall(cfg: Config, card_id: str) -> list[str]:
    """One alert per live session without progress for stall_minutes (CONTRACTS.md §9.3)."""
    win = window.get(cfg.root)
    wt = Git(cfg.root).worktree_for(story_branch(card_id))
    if not wt:
        return []
    git = Git(wt)
    limit = cfg.lever("stall_minutes") * 60
    stalled = []
    for role, info in win.sessions(card_id).items():
        if not info.get("session_id") or win.role_alive(card_id, role) is False:
            continue
        idle = time.time() - _progress(git, wt, card_id, info)
        if idle > limit:
            stalled.append(role)
            if notify.notify(cfg.root, f"{card_id}:stall:{info['session_id']}", "stalled",
                             notify.subject(card_id, cards.titles(git).get(card_id, ""), "bloqué"),
                             f"{role} sans avancée depuis {int(idle // 60)} min"):
                journal.record(journal.event(
                    cfg.root.name, "stall", f"{cards.label_of(Git(cfg.root), card_id)}: {role} idle for {int(idle // 60)} min", story=card_id,
                    evidence=str(transcript_path(info.get("cwd", ""), info["session_id"]))))
    return stalled


def scan(cfg: Config) -> None:
    """Stall detection and healing of every open story (a missed hook, a dead session). An
    error on one story (forge or network down) is reported and the sweep goes on."""
    for cid in open_ids(cfg):
        try:
            check_stall(cfg, cid)
            st = state(cfg, cid)
            if st.engine_next and st.name != "submitted" and not _alive(cfg, cid):
                next_step(cfg, cid)
        except DeliveryError as exc:
            eprint(f"deliveryctl: {cards.label_of(Git(cfg.root), cid)}: {exc.message}")


def wait(cfg: Config, card_id: str, timeout: int = 540, until: str = "checkpoint") -> State:
    """Chain the story until a stop or the timeout, sweeping the other open stories (§9.3).
    A passing error (forge, network) is reported and the wait goes on."""
    deadline = time.time() + timeout
    fetched = 0.0
    stops = STOPPED + ("merged", "closed")
    if until != "merged" and cfg.integration == "human":
        stops += ("submitted",)
    st = state(cfg, card_id)
    while True:
        try:
            st = state(cfg, card_id)
            if st.name in stops:
                return st
            if st.engine_next and not _alive(cfg, card_id):
                st = next_step(cfg, card_id)
                if st.name in stops:
                    return st
            scan(cfg)
            if st.name == "submitted" and time.time() - fetched > 60:
                fetched = time.time()
                Git(cfg.root).fetch()
                if cfg.integration == "ai":
                    next_step(cfg, card_id)
        except DeliveryError as exc:
            eprint(f"deliveryctl: {label(st)}: {exc.message}")
            st.detail = f"last error, retried: {exc.message.splitlines()[0][:160]}"
        if time.time() >= deadline:
            st.detail = (st.detail + "; " if st.detail else "") + "still running: wait again"
            st.extra["timeout"] = True
            return st
        time.sleep(10)


def describe(cfg: Config, card_id: str) -> str:
    """State plus the role sessions running, for status displays."""
    st = state(cfg, card_id)
    alive = _alive(cfg, card_id) if st.worktree else []
    if alive:
        st.detail = (st.detail + "; " if st.detail else "") + f"session running: {', '.join(alive)}"
        st.engine_next = ""
    return render(st)


def render(st: State) -> str:
    lines = [f"{label(st)} — {st.name}"]
    if st.worktree:
        lines.append(f"  worktree: {st.worktree}")
    if st.tree:
        lines.append(f"  code tree: {st.tree}")
    if st.outcome:
        lines.append(f"  outcome: {st.outcome[0]} — {st.outcome[1]}" + ("" if st.fresh else " (stale)"))
    if st.verify_fails or st.review_noes:
        lines.append(f"  red verifications: {st.verify_fails}, rejected reviews: {st.review_noes}")
    if st.detail:
        lines.append(f"  {st.detail}")
    if st.extra.get("mr"):
        lines.append(f"  merge request: {st.extra['mr'].get('url')} ({st.extra['mr'].get('checks')})")
    if st.engine_next:
        lines.append(f"  engine next: {st.engine_next}")
    if st.human_next:
        lines.append(f"  your next gesture: {st.human_next}")
    return "\n".join(lines)


def open_ids(cfg: Config) -> list[str]:
    out = []
    for item in Git(cfg.root).worktrees():
        branch = str(item.get("branch", ""))
        if branch.startswith("refs/heads/story/"):
            out.append(branch.rsplit("/", 1)[-1])
    return sorted(out)


def detach_next(cfg: Config, card_id: str, delay: int = 3) -> None:
    """Run `story next` then a sweep of the open stories in a detached process (the Stop hook
    must return at once)."""
    log = run_dir(cfg.root) / "logs" / "hook.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    engine = Path(__file__).resolve().parents[1]
    env = clean_env()
    env["PYTHONPATH"] = str(engine) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    code = (f"import time; time.sleep({int(delay)}); from deliveryctl.story import after_stop; "
            f"raise SystemExit(after_stop({card_id!r}))")
    with open(log, "a", encoding="utf-8") as out:
        subprocess.Popen([sys.executable, "-c", code], cwd=str(cfg.root), env=env,
                         stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                         start_new_session=True)


def after_stop(card_id: str) -> int:
    """What the Stop hook of a role detaches: `story next <id>`, then a sweep (CONTRACTS.md §9.3)."""
    from .cli import main
    from .config import load
    from .core import main_root
    code = main(["story", "next", card_id])
    try:
        scan(load(main_root()))
    except DeliveryError as exc:
        eprint(f"deliveryctl: sweep: {exc.message}")
    return code
