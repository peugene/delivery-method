"""Test window: runs the command named by DELIVERY_FAKE_AGENT instead of claude, synchronously,
so end-to-end tests exercise the whole story cycle without a model."""

from __future__ import annotations

import os
import subprocess
import sys

from ..core import clean_env
from .base import Window


class FakeWindow(Window):
    name = "fake"
    headless = True

    def start_role(self, card_id: str, role: str, spec: dict) -> dict:
        agent = os.environ.get("DELIVERY_FAKE_AGENT")
        env = clean_env(spec["env"])
        for key in ("DELIVERY_FAKE_AGENT", "DELIVERY_FAKE_WINDOW"):
            if os.environ.get(key):
                env[key] = os.environ[key]
        for key, value in os.environ.items():
            if key.startswith("FAKE_"):
                env[key] = value
        env["DELIVERY_SESSION_ID"] = spec["session_id"]
        info = {"pid": None, "session_id": spec["session_id"], "name": spec["name"], "cwd": spec["cwd"]}
        self.remember(card_id, role, info)
        if agent:
            proc = subprocess.run([sys.executable, agent, role, card_id, spec["argv"][-1]],
                                  cwd=spec["cwd"], env=env, text=True, capture_output=True)
            info["exit"] = proc.returncode
            info["output"] = (proc.stdout + proc.stderr)[-2000:]
            self.remember(card_id, role, info)
        return info

    def role_alive(self, card_id: str, role: str) -> bool | None:
        """Sessions run synchronously, so they are over; FAKE_ALIVE lists the roles to show as
        alive (a session still working, for the tests of §9.1 and §9.3)."""
        return role in os.environ.get("FAKE_ALIVE", "").split(",")
