"""`deliveryctl run`: start the technical-lead in run mode on the ready cards (CONTRACTS.md
§12.2). The lead chains the stories through the engine verbs; the engine chains the roles of
each story."""

from __future__ import annotations

import os
import shutil

from . import cards, roles, window
from .campaign import open_campaign
from .config import Config
from .core import EXIT_OK, EXIT_PRECONDITION, EXIT_TOOL, clean_env, fail, today
from .gitops import Git


def start(cfg: Config, campaign: str | None = None) -> int:
    git = Git(cfg.root)
    git.fetch()
    target = git.target_ref()
    ready = cards.order(cards.load_from_rev(git, target), cards.merged_ids(git))
    if not ready:
        fail(EXIT_PRECONDITION, "no ready card to run (a card becomes ready by a commit of the decision owner)")
    problems = [p for p in cards.lint(cards.load_from_rev(git, target)) if p[0] in {c.id for c, _ in ready}]
    if problems:
        fail(EXIT_PRECONDITION, "ready cards with problems:\n  " + "\n  ".join(f"{w}: {p}" for w, p in problems))
    name = campaign or f"run-{today()}"
    print(open_campaign(cfg, name, "impl"))
    if not shutil.which("claude"):
        fail(EXIT_TOOL, "the 'claude' command is not available")
    prompt = roles.PROMPTS["technical-lead"].format(campaign=name)
    win = window.get(cfg.root)
    spec = roles.launch(cfg, "technical-lead", cfg.root, "lead", prompt, headless=False,
                        extra_env={"DELIVERY_CAMPAIGN": name})
    print("ready cards: " + ", ".join(c.id for c, _ in ready))
    if hasattr(win, "start_lead"):
        info = win.start_lead(spec)
        if info:
            print(f"technical-lead started in window {win.name} ({info.get('pane', '?')})")
            return EXIT_OK
    env = clean_env(spec["env"])
    os.chdir(spec["cwd"])
    os.execvpe(spec["argv"][0], spec["argv"], env)
    return EXIT_OK
