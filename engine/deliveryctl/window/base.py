"""Window contract shared by every implementation."""

from __future__ import annotations

import os
import signal
from pathlib import Path

import json
import shutil
import subprocess

from ..core import now_iso, read_json, run_dir, write_json


def claude_sessions() -> dict | None:
    """Live Claude sessions by session id (`claude agents --json`); None when unknown."""
    if not shutil.which("claude"):
        return None
    try:
        proc = subprocess.run(["claude", "agents", "--json"], text=True, capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    items = data if isinstance(data, list) else data.get("agents") or data.get("sessions") or []
    return {str(i.get("sessionId") or i.get("session_id")): i for i in items if isinstance(i, dict)}


class Window:
    name = "base"
    headless = True

    def __init__(self, root: Path):
        self.root = Path(root)

    # -- session registry (engine-owned, under .delivery/run/sessions) ----------------------
    def _registry(self, card_id: str) -> Path:
        return run_dir(self.root) / "sessions" / f"{card_id}.json"

    def sessions(self, card_id: str) -> dict:
        return read_json(self._registry(card_id), {})

    def remember(self, card_id: str, role: str, data: dict) -> None:
        reg = self.sessions(card_id)
        data = dict(data, started=now_iso(), window=self.name)
        reg[role] = data
        write_json(self._registry(card_id), reg)

    def session(self, card_id: str, role: str) -> dict | None:
        return self.sessions(card_id).get(role)

    # -- operations -------------------------------------------------------------------------
    def probe(self) -> bool:
        return True

    def open_story(self, card_id: str, worktree: Path) -> None:
        """Make the story visible (idempotent)."""

    def start_role(self, card_id: str, role: str, spec: dict) -> dict:
        raise NotImplementedError

    def role_alive(self, card_id: str, role: str) -> bool | None:
        """True / False when known, None when the window cannot tell."""
        info = self.session(card_id, role)
        pid = (info or {}).get("pid")
        if not pid:
            sessions = claude_sessions()
            sid = (info or {}).get("session_id")
            if sessions is None or not sid:
                return None
            return sid in sessions
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def stop_role(self, card_id: str, role: str) -> None:
        info = self.session(card_id, role) or {}
        pid = info.get("pid")
        if pid:
            try:
                os.killpg(int(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

    def show_state(self, card_id: str, state: str) -> None:
        """Surface the story state (a sidebar token in herdr; nothing in a terminal)."""

    def close_story(self, card_id: str) -> None:
        """Remove what open_story created (never the worktree: git owns it)."""
