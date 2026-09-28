"""herdr window: one workspace per story on its git worktree, with an agent pane, a status
pane and a live test log pane. This module is the only part of the kit that knows herdr.
Every call is bounded; when herdr does not answer, the engine goes on in terminal mode."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from ..core import read_json, run_dir, write_json
from .base import Window, claude_sessions

TIMEOUT = 5
STARTING = 90          # seconds a new session may take to appear in `claude agents`


def _herdr(*args, timeout=TIMEOUT) -> dict | None:
    try:
        proc = subprocess.run(["herdr", *args], text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def _age(stamp) -> float:
    """Seconds since an ISO time written by Window.remember; infinite when unreadable."""
    try:
        started = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - started).total_seconds()


def _find(data, key):
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            found = _find(value, key)
            if found is not None:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find(value, key)
            if found is not None:
                return found
    return None


class HerdrWindow(Window):
    name = "herdr"
    headless = False

    def probe(self) -> bool:
        if not shutil.which("herdr"):
            return False
        try:
            proc = subprocess.run(["herdr", "status", "server"], capture_output=True, timeout=TIMEOUT)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return proc.returncode == 0

    def _layout_file(self, card_id: str) -> Path:
        return run_dir(self.root) / "windows" / f"{card_id}.json"

    def layout(self, card_id: str) -> dict:
        return read_json(self._layout_file(card_id), {})

    def _pane_alive(self, pane: str) -> bool:
        return _herdr("pane", "get", pane) is not None

    def open_story(self, card_id: str, worktree: Path) -> None:
        lay = self.layout(card_id)
        if lay.get("agent") and self._pane_alive(lay["agent"]):
            return
        from ..cards import label, titles
        from ..core import ID_RX
        from ..gitops import Git
        is_card = bool(ID_RX.match(card_id))
        # the workspace is named like the card: '<repo>-<id> : <short title>'
        name = label(f"{self.root.name}-{card_id}", titles(Git(self.root)).get(card_id, "") if is_card else "")
        created = _herdr("workspace", "create", "--cwd", str(worktree), "--label", name, "--no-focus")
        ws = _find(created, "workspace_id")
        if not ws:
            return
        panes = _herdr("pane", "list") or {}
        agent = next((p["pane_id"] for p in _find(panes, "panes") or [] if p.get("workspace_id") == ws), None)
        if not agent:
            return
        status = tests = None
        if is_card:
            status = _find(_herdr("pane", "split", agent, "--direction", "right", "--no-focus"), "pane_id")
            tests = _find(_herdr("pane", "split", status, "--direction", "down", "--no-focus"), "pane_id") if status else None
        for pane, title in ((agent, "agent"), (status, "status"), (tests, "tests")):
            if pane:
                _herdr("pane", "rename", pane, title)
        if status:
            engine = self.root / ".delivery" / "deliveryctl"
            cmd = shlex.quote(str(engine)) if engine.exists() else "deliveryctl"
            _herdr("pane", "run", status, f"{cmd} story status {card_id} --watch")
        if tests:
            log = Path(worktree) / "docs" / "stories" / card_id / "work" / "verify.log"
            _herdr("pane", "run", tests, f"touch {shlex.quote(str(log))} && tail -F {shlex.quote(str(log))}")
        write_json(self._layout_file(card_id), {"workspace": ws, "agent": agent, "status": status, "tests": tests})

    def start_role(self, card_id: str, role: str, spec: dict) -> dict:
        lay = self.layout(card_id)
        pane = lay.get("agent")
        if not pane or not self._pane_alive(pane):
            self.open_story(card_id, Path(spec["cwd"]))
            pane = self.layout(card_id).get("agent")
        if not pane:
            from .terminal import TerminalWindow
            return TerminalWindow(self.root).start_role(card_id, role, spec)
        env = " ".join(f"{k}={shlex.quote(v)}" for k, v in spec["env"].items())
        line = f"cd {shlex.quote(spec['cwd'])} && {env} {shlex.join(spec['argv'])}"
        _herdr("pane", "run", pane, line)
        info = {"pane": pane, "session_id": spec["session_id"], "name": spec["name"], "cwd": spec["cwd"]}
        self.remember(card_id, role, info)
        return info

    def start_lead(self, spec: dict) -> dict:
        created = _herdr("workspace", "create", "--cwd", spec["cwd"], "--label",
                         f"{self.root.name}-lead", "--no-focus")
        ws = _find(created, "workspace_id")
        panes = _herdr("pane", "list") or {}
        pane = next((p["pane_id"] for p in _find(panes, "panes") or [] if p.get("workspace_id") == ws), None)
        if not pane:
            return {}
        env = " ".join(f"{k}={shlex.quote(v)}" for k, v in spec["env"].items())
        _herdr("pane", "rename", pane, "technical-lead")
        _herdr("pane", "run", pane, f"cd {shlex.quote(spec['cwd'])} && {env} {shlex.join(spec['argv'])}")
        return {"workspace": ws, "pane": pane}

    def role_alive(self, card_id: str, role: str) -> bool | None:
        """Listed by `claude agents`; None (unknown) while a session started less than
        STARTING seconds ago is not listed yet, so that it is not started a second time."""
        info = self.session(card_id, role) or {}
        sid = info.get("session_id")
        sessions = claude_sessions()
        if sessions is None or not sid:
            return None
        if sid in sessions:
            return True
        return None if _age(info.get("started")) < STARTING else False

    def stop_role(self, card_id: str, role: str) -> None:
        info = self.session(card_id, role) or {}
        pane = info.get("pane")
        if pane:
            _herdr("pane", "send-text", pane, "/exit")
            _herdr("pane", "send-keys", pane, "enter")
            for _ in range(20):
                if not self.role_alive(card_id, role):
                    return
                time.sleep(1)

    def show_state(self, card_id: str, state: str) -> None:
        ws = self.layout(card_id).get("workspace")
        if ws:
            _herdr("workspace", "report-metadata", "--source", "delivery-method", "--token", f"state={state}", ws)

    def close_story(self, card_id: str) -> None:
        ws = self.layout(card_id).get("workspace")
        if ws:
            _herdr("workspace", "close", ws)
        self._layout_file(card_id).unlink(missing_ok=True)
