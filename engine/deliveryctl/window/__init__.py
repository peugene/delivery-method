"""Where role sessions run. The engine reads story state from git and files only; a window
merely shows sessions and starts them. Three implementations: 'terminal' (plain processes),
'herdr' (one workspace per story) and 'fake' (tests)."""

from __future__ import annotations

import os
from pathlib import Path

from .. import config
from .base import Window


def get(root: Path) -> Window:
    choice = config.machine().get("window", "auto")
    if os.environ.get("DELIVERY_FAKE_WINDOW"):
        from .fake import FakeWindow
        return FakeWindow(root)
    if choice in ("auto", "herdr"):
        from .herdr import HerdrWindow
        win = HerdrWindow(root)
        if win.probe():
            return win
        if choice == "herdr":
            from ..core import eprint
            eprint("window = herdr but herdr does not answer: falling back to 'terminal'")
    from .terminal import TerminalWindow
    return TerminalWindow(root)
