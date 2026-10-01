"""Cloud window: the story-implementer runs as a Claude Code cloud session, so that the work goes
on when this computer sleeps or goes offline. Used for that role only, whatever the machine's
window; it shows nothing itself (`story status` shows the session URL) and cannot stop a session."""

from __future__ import annotations

import fcntl
import os
import re
import select
import signal
import struct
import subprocess
import termios
import time
from pathlib import Path

from ..core import EXIT_PRECONDITION, EXIT_TOOL, clean_env, fail, now_iso
from ..gitops import Git
from .base import Window

LAUNCH_TIMEOUT = 180       # seconds `claude --cloud` may take to create the session
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
TRUST_DIALOG = "Is this a project you created or one you trust"      # compared without whitespace
VIEW = re.compile(r"^\s*View:\s*(https://\S+)", re.MULTILINE)


def _asks_trust(raw: bytes) -> bool:
    text = ANSI.sub("", raw.decode("utf-8", "replace"))
    return "".join(TRUST_DIALOG.split()) in "".join(text.split())


def run_in_terminal(argv: list[str], cwd: str, env: dict, timeout: int) -> tuple[int, str]:
    """Run a command with a pseudo-terminal as its input and output (`claude --cloud` refuses
    to run without one); returns its exit code and its output without terminal escapes. Fails at
    once when the output shows Claude Code's trust dialog: nobody answers it here."""
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 500, 0, 0))   # no wrapped URL
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=slave, stdout=slave, stderr=slave,
                                start_new_session=True)
    except OSError as exc:
        os.close(master)
        os.close(slave)
        fail(EXIT_TOOL, f"cannot run {argv[0]}: {exc}")
    os.close(slave)
    chunks, deadline = [], time.monotonic() + timeout
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                fail(EXIT_TOOL, f"timeout after {timeout}s: {argv[0]} {argv[1]}")
            if not select.select([master], [], [], min(left, 1.0))[0]:
                continue
            try:
                data = os.read(master, 4096)
            except OSError:            # the last writer is gone: end of output
                break
            if not data:
                break
            chunks.append(data)
            if _asks_trust(b"".join(chunks)):
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                fail(EXIT_PRECONDITION, f"Claude Code has no accepted trust for {cwd}: start 'claude' once in the "
                                        "repository's main checkout and accept the trust dialog (story working "
                                        "copies inherit that trust), or trust the folder of the story working copies")
    finally:
        os.close(master)
    code = proc.wait()
    text = ANSI.sub("", b"".join(chunks).decode("utf-8", "replace")).replace("\r", "")
    return code, text.strip()


def parse_view(output: str) -> tuple[str, str] | None:
    """(session id, URL without its query string) from the `View:` line, or None."""
    found = VIEW.search(output)
    if not found:
        return None
    url = found.group(1).split("?", 1)[0].rstrip("/")
    return url.rsplit("/", 1)[-1], url


class CloudWindow(Window):
    name = "cloud"
    headless = True

    def start_role(self, card_id: str, role: str, spec: dict) -> dict:
        cwd, branch = spec["cwd"], spec["branch"]
        git = Git(Path(cwd))
        git.push(branch)       # the session is cloned from the pushed branch; a diverged remote refuses
        head = git.head()
        pushed_at = now_iso()
        code, output = run_in_terminal(spec["argv"], cwd, clean_env(spec["env"]), LAUNCH_TIMEOUT)
        view = parse_view(output)
        if code != 0 or not view:
            fail(EXIT_TOOL, f"claude --cloud failed ({code}): "
                            + ("no 'View:' line in its output\n" if code == 0 else "\n") + output)
        info = {"session_id": view[0], "url": view[1], "head": head, "pushed_at": pushed_at,
                "name": spec["name"], "cwd": cwd}
        self.remember(card_id, role, info)
        return info

    def role_alive(self, card_id: str, role: str) -> bool | None:
        """A cloud session cannot be queried from here: it lives until the engine marks the
        entry `ended`."""
        info = self.session(card_id, role)
        return bool(info) and "ended" not in info

    def stop_role(self, card_id: str, role: str) -> None:
        """A cloud session cannot be stopped from here."""
