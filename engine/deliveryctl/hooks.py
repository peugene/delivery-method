"""Method hooks (CONTRACTS.md §9.2). They run in every session of an equipped project (its
.claude/settings.json) and of a project where the plugin is enabled, so outside role sessions
they return at once, silently, except for the toast of a human-led session that waits on
'Outcome: question'. The engine modules are imported only past the role test, so that an
unsupported Python stays silent outside role sessions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

from .core import ID_RX, main_root, repo_root

OUTCOME_RX = re.compile(r"^Outcome:\s*(done|blocked|deferred|plan-ready|question)\b")
LEAD_OUTCOMES = ("done", "blocked")
BLOCK = {
    "technical-lead": "The run does not stop for a question: decide and record it, or defer the card, "
                      "then go on with the next launchable card. When nothing is launchable, rewrite the "
                      "'## Run' section of the campaign, then end your last message with "
                      "'Outcome: done — <summary>' ('Outcome: blocked — <reason>' when the run cannot go on).",
    "default": "Finish your work, then end your last message with the exact Outcome line your "
               "'Ends with' section gives.",
}
DENIAL_MARKS = ("Permission to use", "denied")


def _stdin() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, OSError):
        return {}


def _last_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def last_outcome(text: str):
    """The Outcome line of a message: its last non-empty line only (CONTRACTS.md §7.4)."""
    return OUTCOME_RX.match(_last_line(text))


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def _human_question(data: dict, notify_owner: bool = True) -> int:
    """A human-led session that ends its turn on 'Outcome: question' waits for the owner."""
    last = data.get("last_assistant_message") or ""
    found = last_outcome(last)
    if not found or found.group(1) != "question" or not notify_owner:
        return 0
    try:
        from . import config, notify
        cfg = config.load(main_root(Path(data.get("cwd") or ".")))
        notify.notify(cfg.root, f"question:{data.get('session_id', '')}:{_digest(last)}", "decision",
                      "décision attendue", _last_line(last)[:180])
    except Exception:
        pass
    return 0


def _review_problems(cwd: Path, card_id: str) -> list[str]:
    """What keeps review.md, at HEAD of the reviewer's worktree, from being a valid verdict on
    the current code tree."""
    from . import verdict as vd
    from .gitops import Git
    rel = f"docs/stories/{card_id}/review.md"
    git = Git(cwd)
    tree = git.code_tree()
    text = git.show("HEAD", rel)
    if text is None:
        problems = ["it is not committed"]
    else:
        parsed = vd.parse(text, "review")
        if parsed is None:
            problems = ["its last lines are not a verdict block"]
        else:
            problems = list(parsed.problems)
            if parsed.tree and parsed.tree != tree:
                problems.append(f"Tree {parsed.tree} is not the current code tree")
        if git.run("status", "--porcelain", "--", rel).stdout.strip():
            problems.append("it has uncommitted changes")
    if not problems:
        return []
    return [f"{rel}: {'; '.join(problems)}. Fix its verdict block (the last lines, 'Tree: {tree}'), "
            "commit it, then end with your Outcome line."]


def _denied(content) -> bool:
    if isinstance(content, list):
        content = " ".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return isinstance(content, str) and all(mark in content for mark in DENIAL_MARKS)


def _record_refusals(cfg, role: str, scope: str, data: dict) -> None:
    """Carry to the journal, once, the permission refusals of the session transcript that were
    not carried yet (an interactive session has no JSON log for the engine to read)."""
    from . import journal
    from .core import file_lock, read_json, run_dir, write_json
    path = Path(data.get("transcript_path") or "")
    session_id = str(data.get("session_id") or "")
    if not session_id or not path.is_file():
        return
    uses, denied = {}, []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"tool_use"' not in line and not ('"tool_result"' in line and DENIAL_MARKS[0] in line):
                continue
            try:
                content = (json.loads(line).get("message") or {}).get("content")
            except (json.JSONDecodeError, AttributeError):
                continue
            for item in content if isinstance(content, list) else []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "tool_use":
                    uses[item.get("id")] = item
                elif item.get("type") == "tool_result" and item.get("is_error") and _denied(item.get("content")):
                    denied.append(item.get("tool_use_id"))
    runs = run_dir(cfg.root)
    with file_lock(runs / "refusals.lock"):
        registry = read_json(runs / "refusals.json", {})
        new = denied[int(registry.get(session_id, 0)):]
        registry[session_id] = len(denied)
        write_json(runs / "refusals.json", registry)
    # the transcript is read: the engine's reading of a headless log would count them twice
    sessions = runs / "sessions" / f"{scope}.json"
    reg = read_json(sessions, {})
    if isinstance(reg.get(role), dict) and reg[role].get("session_id") == session_id:
        reg[role].update(denials_recorded=True, denials=len(denied))
        write_json(sessions, reg)
    if not new:
        return
    shown = []
    for use_id in new[:10]:
        use = uses.get(use_id) or {}
        tool_input = use.get("input") or {}
        what = tool_input.get("command") or tool_input.get("file_path") or tool_input.get("path") or ""
        shown.append(f"{use.get('name', '?')}: {' '.join(str(what).split())[:160]}")
    from . import cards
    from .gitops import Git
    scope_name = cards.label_of(Git(cfg.root), scope) if ID_RX.match(scope) else scope
    journal.record(journal.event(cfg.root.name, "refusal",
                                 f"{role} ({scope_name}), {len(new)} refusal(s): " + " | ".join(shown),
                                 story=scope if ID_RX.match(scope) else "", role=role, evidence=str(path)))


def _cloud() -> bool:
    return os.environ.get("CLAUDE_CODE_REMOTE") == "true"


def _cloud_story(cwd: Path):
    """The story a cloud session serves, found from its branch; None when it serves none."""
    from .gate import story_of_branch
    from .gitops import Git
    try:
        return story_of_branch(Git(cwd))
    except Exception:
        return None


def _cloud_problems(cwd: Path, story_id: str, last: str) -> list[str]:
    """What the engine, on the owner's computer, would not find in the pushed branch."""
    from .gitops import Git
    from .verify import story_dir
    git = Git(cwd)
    report = f"{story_dir(story_id)}/report.md"
    problems = []
    if not last_outcome(last):
        problems.append("End your last message with the exact Outcome line the 'Ends with' section of "
                        ".claude/agents/story-implementer.md gives.")
    if git.run("status", "--porcelain", "--", report, check=False).stdout.strip():
        problems.append(f"Commit {report}: it has uncommitted changes.")
    upstream = git.rev("@{upstream}")
    if not upstream or git.out("rev-list", "--count", "@{upstream}..HEAD", check=False) not in ("", "0"):
        problems.append("Push the working branch with 'git push -u origin HEAD': it has commits "
                        "that its upstream lacks.")
    return problems


def _cloud_stop(data: dict) -> int:
    """A cloud session never chains and never notifies: the engine on the owner's computer picks
    the work up from the pushed branch. In a story session the first stop is checked."""
    story_id = _cloud_story(Path(data.get("cwd") or "."))
    if not story_id:
        return _human_question(data, notify_owner=False)
    problems = _cloud_problems(Path(data.get("cwd") or "."), story_id, data.get("last_assistant_message") or "")
    if problems and not data.get("stop_hook_active"):
        print(json.dumps({"decision": "block", "reason": " ".join(problems)}))
    return 0


def stop() -> int:
    role = os.environ.get("DELIVERY_ROLE")
    if _cloud() and not role:
        return _cloud_stop(_stdin())
    if not role:
        return _human_question(_stdin())
    from . import config, journal, notify, story
    data = _stdin()
    last = data.get("last_assistant_message") or ""
    scope = os.environ.get("DELIVERY_STORY", "")
    try:
        cfg = config.load(main_root())
    except Exception:
        cfg = None
    if cfg:
        try:
            _record_refusals(cfg, role, scope, data)
        except Exception:
            pass
    found = last_outcome(last)
    if found and role == "technical-lead" and found.group(1) not in LEAD_OUTCOMES:
        found = None
    problems = [] if found else [BLOCK.get(role, BLOCK["default"])]
    if role == "story-reviewer" and ID_RX.match(scope):
        try:
            problems += _review_problems(Path(data.get("cwd") or "."), scope)
        except Exception:
            pass
    if problems and not data.get("stop_hook_active"):
        print(json.dumps({"decision": "block", "reason": " ".join(problems)}))
        return 0
    if not found and role == "technical-lead" and cfg and data.get("stop_hook_active"):
        # second stop without an Outcome: the run has stopped and nothing else watches the lead
        if notify.notify(cfg.root, f"lead-stall:{data.get('session_id', '')}", "stalled",
                         "run arrêté sans Outcome", "le technical-lead s'est arrêté deux fois sans ligne Outcome"):
            journal.record(journal.event(cfg.root.name, "stall", "technical-lead stopped twice without an Outcome line",
                                         role=role, evidence=str(data.get("transcript_path", ""))))
        return 0
    if not found or not cfg:
        return 0
    line = _last_line(last)
    if role == "technical-lead":
        done = found.group(1) == "done"
        notify.notify(cfg.root, f"run:{data.get('session_id', '')}:{_digest(line)}",
                      "done" if done else "decision", "run terminé" if done else "run arrêté",
                      line[:180] + " — voir la section ## Run de la campagne")
        journal.record(journal.event(cfg.root.name, "summary", last[-1500:], role=role, source="engine"))
        return 0
    if role in ("story-implementer", "story-reviewer") and scope:
        story.detach_next(cfg, scope)
    elif role == "qualification-runner" and not scope.startswith("nightly-"):
        # the night run notifies by itself when it ends (§16)
        notify.notify(cfg.root, f"qualification:{data.get('session_id', '')}", "decision",
                      f"recette {scope} : résultats à synthétiser", line[:180])
    return 0


def _put_on_path() -> None:
    """Make 'deliveryctl' resolve to the project copy in every later Bash command of the session,
    local or cloud (the plugin's bin/ is not on the PATH once the plugin is disabled here)."""
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        return
    root = os.environ.get("CLAUDE_PROJECT_DIR") or str(repo_root())
    if not (Path(root) / ".delivery" / "deliveryctl").exists():
        return
    with open(env_file, "a", encoding="utf-8") as fh:
        fh.write(f'export PATH="{root}/.delivery:$PATH"\n')


def session_start() -> int:
    """At every session start: put the project copy of the engine on the PATH. After a compaction,
    also remind a role where its state lives."""
    data = _stdin()
    try:
        _put_on_path()
    except Exception:
        pass
    role = os.environ.get("DELIVERY_ROLE")
    if _cloud() and not role and data.get("source") in ("startup", "resume"):
        story_id = _cloud_story(Path(data.get("cwd") or "."))
        if story_id:
            print(f"This session is the story-implementer of story {story_id}: read "
                  f".claude/agents/story-implementer.md, then docs/stories/{story_id}/order.md, plan.md "
                  "and work/notes.md when they exist, then git status.")
            sys.stdout.flush()
    if not role or data.get("source") != "compact":
        return 0
    scope = os.environ.get("DELIVERY_STORY", "<id>")
    reread = {
        "technical-lead": f"the '## Next' and '## Run' sections of docs/campaigns/{os.environ.get('DELIVERY_CAMPAIGN', '<name>')}.md, "
                          "then 'deliveryctl story status'",
        "qualification-runner": "qualification/order.md, qualification/work/notes.md, then git status",
    }.get(role, f"docs/stories/{scope}/order.md, plan.md, work/notes.md, then git status")
    print(f"Context was compacted. The files are the state: re-read {reread}, before going on.")
    sys.stdout.flush()
    try:
        from . import journal
        root = main_root()
        journal.record(journal.event(root.name, "compact", f"{role} compacted",
                                     story=os.environ.get("DELIVERY_STORY", ""), role=role))
    except Exception:
        pass
    return 0
