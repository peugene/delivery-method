"""Toasts, sent by the engine only, once per event (CONTRACTS.md §13)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import config
from .core import eprint, file_lock, now_iso, read_json, run_dir, write_json

ICONS = {"decision": "⚠", "done": "⭐", "stalled": "🚨", "night": "⭐", "story-end": "⭐"}


def notify(root: Path, key: str, kind: str, subject: str, message: str) -> bool:
    """Send one toast for the event `key`; an event already notified is not sent again.
    Returns True when the event is new, whatever the channel: the toast of notify_cmd, or the
    error output when notify_cmd is empty or fails. A failing notify_cmd (not started, timed
    out or non-zero exit) prints '[notification failed: <its error>] <title> — <message>' on
    the error output; the event stays notified, it is not retried."""
    runs = run_dir(root)
    registry = runs / "notified.json"
    with file_lock(runs / "notified.lock"):
        seen = read_json(registry, {})
        if key in seen:
            return False
        seen[key] = now_iso()
        write_json(registry, seen)
    repo = Path(root).name
    title = f"{ICONS.get(kind, '⭐')} {repo} — {subject}"
    raw = os.path.expanduser(config.machine().get("notify_cmd") or "")
    cmd = raw if (raw and os.access(raw, os.X_OK)) else (shutil.which(raw) if raw else None)
    if not cmd:
        eprint(f"[notification] {title} — {message}")
        return True
    try:
        proc = subprocess.run([cmd, title, message], timeout=15, capture_output=True, text=True)
        error = "" if proc.returncode == 0 else \
            ((proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        error = str(exc)
    if error:
        eprint(f"[notification failed: {' '.join(error.split())[:200]}] {title} — {message}")
    return True


def forget(root: Path, prefix: str) -> None:
    """Allow events of a story to be notified again (a new loop, a reopened story)."""
    runs = run_dir(root)
    registry = runs / "notified.json"
    with file_lock(runs / "notified.lock"):
        seen = read_json(registry, {})
        kept = {k: v for k, v in seen.items() if not k.startswith(prefix)}
        if kept != seen:
            write_json(registry, kept)
