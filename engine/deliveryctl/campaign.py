"""Campaigns: the state file of a lead (CONTRACTS.md §12.3). No branch: the lead commits on the
current branch of the main checkout, without pushing; the decision owner brings the result
to the target branch."""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .core import check_slug, today

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "campaign" / "campaign.md"


def state_file(root: Path, name: str) -> Path:
    return Path(root) / "docs" / "campaigns" / f"{name}.md"


def open_campaign(cfg: Config, name: str, phase: str) -> str:
    check_slug(name, "campaign name")
    path = state_file(cfg.root, name)
    (cfg.root / "docs" / "campaigns" / "work" / name).mkdir(parents=True, exist_ok=True)
    if path.exists():
        return f"campaign {name}: {path.relative_to(cfg.root)} (existing)"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = TEMPLATE.read_text(encoding="utf-8") if TEMPLATE.exists() else \
        "## Objective\n\n## Questions\n\n## Run\n\n## Next\n"
    text = text.replace("<name>", name).replace("<phase>", phase).replace("<date>", today())
    path.write_text(text, encoding="utf-8")
    return f"campaign {name}: {path.relative_to(cfg.root)} (created, not committed)"
