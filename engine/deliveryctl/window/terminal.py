"""Window without a multiplexer: role sessions run as detached headless processes whose
output goes to a log file; `deliveryctl story status --watch` shows where things stand."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..core import clean_env, run_dir
from .base import Window


class TerminalWindow(Window):
    name = "terminal"
    headless = True

    def log_path(self, card_id: str, role: str) -> Path:
        path = run_dir(self.root) / "logs" / f"{card_id}-{role}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def start_role(self, card_id: str, role: str, spec: dict) -> dict:
        log = self.log_path(card_id, role)
        env = clean_env(spec["env"])
        with open(log, "ab") as out:
            proc = subprocess.Popen(
                spec["argv"], cwd=spec["cwd"], env=env, stdin=subprocess.DEVNULL,
                stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
            )
        info = {"pid": proc.pid, "session_id": spec["session_id"], "log": str(log),
                "name": spec["name"], "cwd": spec["cwd"]}
        self.remember(card_id, role, info)
        return info
