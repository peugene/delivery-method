"""Fake qualification-runner for tests: no model. On a nightly prompt it writes one anomaly card
with the id and 'found' value the prompt gives, and commits it unless FAKE_RUNNER_NO_COMMIT=1.
On a qualification prompt it records the prompt in qualification/work/runner.txt."""

import os
import re
import subprocess
import sys
from pathlib import Path

role, scope, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
root = Path.cwd()

if prompt.startswith("Nightly"):
    card_id = re.search(r"ids from (a\d+)", prompt).group(1)
    found = re.search(r"found: (\S+?),", prompt).group(1)
    path = root / "backlog" / f"{card_id}-sign-in-fails.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {card_id}\nkind: anomaly\ntitle: Sign in fails\nstatus: to-triage\n"
        f"depends_on: []\nrisks: []\nspec: s001\nfound: {found}\n---\n"
        "## Objective\nSigning in fails.\n## Context and scope\ntest @s001-ac1 fails.\n"
        "## Oracle\n- @s001-ac1 passes.\n- Not tested by this card: nothing else.\n")
    if os.environ.get("FAKE_RUNNER_NO_COMMIT") != "1":
        subprocess.run(["git", "add", "--", str(path)], cwd=root, check=True)
        subprocess.run(["git", "commit", "--quiet", "-m",
                        f"anomaly {card_id}\n\nCampaign: {scope}\nAgent: {role}"], cwd=root, check=True)
else:
    out = root / "qualification" / "work" / "runner.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"{role} {scope} {prompt}\n")
