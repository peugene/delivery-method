"""Project instructions that name the multiplexer. Roles never drive it and story state is
never read from it, so a mention in CLAUDE.md, .claude/ or the project's auto memory is worth
a note from `deliveryctl doctor`. The name stays inside this package."""

from __future__ import annotations

import re
from pathlib import Path

NAME = "herdr"
NAME_RX = re.compile(rf"\b{NAME}\b", re.IGNORECASE)
MAX_BYTES = 1_000_000


def _candidates(root: Path, home: Path) -> list[Path]:
    paths = [root / "CLAUDE.md", root / "CLAUDE.local.md"]
    settings = root / ".claude"
    if settings.is_dir():
        paths += sorted(p for p in settings.rglob("*") if p.is_file())
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(root.resolve()))
    memory = home / ".claude" / "projects" / slug / "memory"
    if memory.is_dir():
        paths += sorted(memory.glob("*.md"))
    return [p for p in paths if p.is_file()]


def files_naming_it(root: Path, home: Path | None = None) -> list[Path]:
    """Files of the project's instructions that name the multiplexer."""
    found = []
    for path in _candidates(Path(root), Path(home) if home else Path.home()):
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if NAME_RX.search(text):
            found.append(path)
    return found
