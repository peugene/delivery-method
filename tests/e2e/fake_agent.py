"""Fake role session for end-to-end tests: plays story-implementer and story-reviewer the way
the contracts say, without a model. Behaviour is steered by environment variables:
FAKE_REVIEW = "no-once" (first review says no), "no" (every review says no), "invalid" (the
verdict block is malformed); FAKE_IMPL = "deferred" (implementer defers), "question" (it stops
on a question), "crash" (it ends without a word); FAKE_BREAK = "1" (the first implementation
breaks the check), "always" (every one does). Each session appends its role and mode to
work/fake-modes, one line per session."""

import os
import re
import subprocess
import sys
from pathlib import Path

role, card, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
root = Path.cwd()
story = root / "docs" / "stories" / card
marker = story / "work" / "fake-state"
marker.parent.mkdir(parents=True, exist_ok=True)
seen = marker.read_text().split() if marker.exists() else []
mode = prompt.split("Mode: ")[-1] if "Mode: " in prompt else "loop " + prompt.split("Loop ")[-1]
with open(story / "work" / "fake-modes", "a") as modes:
    modes.write(f"{role} {mode.rstrip('.')}\n")


def git(*args):
    return subprocess.run(["git", *args], cwd=root, check=True, text=True, capture_output=True).stdout


def commit(paths, subject):
    git("add", "--", *paths)
    git("commit", "--quiet", "-m", f"{subject}\n\nStory: {card}\nAgent: {role}")


if role == "story-implementer":
    if os.environ.get("FAKE_IMPL") == "crash":
        sys.exit(1)
    if os.environ.get("FAKE_IMPL") == "deferred":
        (story / "spec-question.md").write_text("Which order for shared lists?\n")
        (story / "report.md").write_text("## Delivered\nnone\n\nOutcome: deferred — product question\n")
        commit([f"docs/stories/{card}/spec-question.md", f"docs/stories/{card}/report.md"], "defer")
        sys.exit(0)
    if os.environ.get("FAKE_IMPL") == "question":
        (story / "report.md").write_text("## For the decision owner\nwhich order?\n\nOutcome: question — order\n")
        commit([f"docs/stories/{card}/report.md"], "question")
        sys.exit(0)
    if "plan-first" in prompt:
        (story / "plan.md").write_text("- [ ] append the feature line\n")
        (story / "report.md").write_text("## Delivered\nplan only\n\nOutcome: plan-ready — plan written\n")
        commit([f"docs/stories/{card}/plan.md", f"docs/stories/{card}/report.md"], "plan")
        sys.exit(0)
    app = root / "src" / "app.txt"
    if "fix-verification" in prompt:
        app.write_text("".join(l for l in app.read_text().splitlines(True) if "BROKEN" not in l))
    brk = os.environ.get("FAKE_BREAK")
    broken = brk == "always" or (brk == "1" and "broke" not in seen)
    app.write_text(app.read_text() + ("BROKEN\n" if broken else f"feature {card} {len(seen)}\n"))
    commit(["src/app.txt"], f"implement {card}")
    (story / "report.md").write_text(
        "## Delivered\n- src/app.txt\n\n## Deviations\nnone\n\n## Verified points\n- all confirmed\n\n"
        "## Oracle\n- measured\n\n## Proof\n- check\n\n## Findings\nnone\n\n## For the decision owner\nnone\n\n"
        f"Outcome: done — {card} implemented ({prompt.split('Mode: ')[-1].rstrip('.')})\n")
    commit([f"docs/stories/{card}/report.md"], "report")
    seen.append("broke" if broken else "impl")
elif role == "story-reviewer":
    tree = re.search(r"code tree ([0-9a-f]{40})", prompt).group(1)
    how = os.environ.get("FAKE_REVIEW", "")
    verdict = "no" if how == "no" or (how == "no-once" and "reviewed" not in seen) else "yes"
    if how == "invalid":
        verdict = "yes — minor notes only"
    (story / "review.md").write_text(
        f"## Findings\n1. {'naming' if verdict == 'no' else 'none'}\n\nVerdict: {verdict}\nTree: {tree}\n"
        "Command: true\nResult: exit 0\nBy: story-reviewer\n")
    commit([f"docs/stories/{card}/review.md"], "review")
    seen.append("reviewed")
marker.write_text(" ".join(seen))
