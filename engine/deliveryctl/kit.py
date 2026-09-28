"""`deliveryctl kit lint`: checks of the plugin itself (templates of prompts, size caps, no
provenance, isolation of the multiplexer, role permission files)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import frontmatter as fm
from .config import parse as parse_config
from .core import EXIT_OK, EXIT_RED

CAPS = {"rules": 60, "commands": 80, "agents": 60, "skills": 80, "templates": 60}
BUDGET = {"engine": 3500, "prompts": 1800, "templates": 700}
AGENT_KEYS = {"name", "description", "tools", "disallowedTools", "model", "effort", "color", "skills", "maxTurns"}
AGENT_SECTIONS = ("Receives", "May change", "Must not", "Ends with")
COMMAND_KEYS = {"description", "argument-hint", "allowed-tools", "model"}
COMMAND_SECTIONS = ("Contract", "Preconditions", "Steps", "Outputs", "Ends with")
SKILL_KEYS = {"name", "description"}
SKILL_SECTIONS = ("When to use", "Doctrine", "Defaults and levers", "Anti-patterns", "Checks")
GENERIC_PROVENANCE = (r"\b20\d\d-\d\d-\d\d\b", r"\bincident\b", r"\b[A-Z]{2,4} l\.\s?\d")


def provenance_patterns() -> list[re.Pattern]:
    """Generic patterns (dates, incidents, line references to other documents), plus the words of
    a local list named by DELIVERY_KIT_FORBIDDEN (one regular expression per line): names of
    people, projects or clients that must never reach the kit, kept out of the repository."""
    patterns = list(GENERIC_PROVENANCE)
    extra = os.environ.get("DELIVERY_KIT_FORBIDDEN")
    if extra and Path(extra).is_file():
        patterns += [line.strip() for line in Path(extra).read_text(encoding="utf-8").splitlines()
                     if line.strip() and not line.startswith("#")]
    return [re.compile(p, re.IGNORECASE) for p in patterns]


PROMPT_DIRS = ("commands", "agents", "skills", "rules", "templates", "hooks")


def _lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _sections(body: str) -> list[str]:
    return [h for h, _ in fm.sections(body) if h]


def _has(headings: list[str], name: str) -> bool:
    return any(h == name or h.startswith(name + " ") for h in headings)


def lint(root: Path) -> tuple[list[str], list[str]]:
    errors, notes = [], []
    root = Path(root)

    for agent in sorted((root / "agents").glob("*.md")):
        rel = agent.relative_to(root)
        try:
            data, body = fm.load(agent)
        except fm.FrontmatterError as exc:
            errors.append(f"{rel}: {exc.message}")
            continue
        for key in data:
            if key not in AGENT_KEYS:
                errors.append(f"{rel}: unknown frontmatter key '{key}'")
        if data.get("name") != agent.stem:
            errors.append(f"{rel}: name must be '{agent.stem}'")
        for key in ("description", "model"):
            if not data.get(key):
                errors.append(f"{rel}: '{key}' is required")
        for section in AGENT_SECTIONS:
            if not _has(_sections(body), section):
                errors.append(f"{rel}: missing section '## {section}'")

    for command in sorted((root / "commands").glob("*.md")):
        rel = command.relative_to(root)
        try:
            data, body = fm.load(command)
        except fm.FrontmatterError as exc:
            errors.append(f"{rel}: {exc.message}")
            continue
        for key in data:
            if key not in COMMAND_KEYS:
                errors.append(f"{rel}: unknown frontmatter key '{key}'")
        if not data.get("description"):
            errors.append(f"{rel}: 'description' is required")
        headings = _sections(body)
        for section in COMMAND_SECTIONS:
            if not _has(headings, section):
                errors.append(f"{rel}: missing section '## {section}'")
        contract = fm.section_get(body, "Contract") or ""
        if "Regime:" not in contract:
            errors.append(f"{rel}: '## Contract' states the 'Regime:'")

    for skill in sorted((root / "skills").glob("*/SKILL.md")):
        rel = skill.relative_to(root)
        try:
            data, body = fm.load(skill)
        except fm.FrontmatterError as exc:
            errors.append(f"{rel}: {exc.message}")
            continue
        for key in data:
            if key not in SKILL_KEYS:
                errors.append(f"{rel}: unknown frontmatter key '{key}'")
        if data.get("name") != skill.parent.name:
            errors.append(f"{rel}: name must be '{skill.parent.name}'")
        if not data.get("description"):
            errors.append(f"{rel}: 'description' is required")
        for section in SKILL_SECTIONS:
            if not _has(_sections(body), section):
                errors.append(f"{rel}: missing section '## {section}'")

    for folder, cap in CAPS.items():
        base = root / folder
        if not base.exists():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file() and p.suffix in (".md", ".toml", ".json", ".yml", ".ts")):
            count = _lines(path)
            if count > cap:
                errors.append(f"{path.relative_to(root)}: {count} lines (cap {cap})")

    for folder in PROMPT_DIRS:
        base = root / folder
        if not base.exists():
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            text = path.read_text(encoding="utf-8", errors="replace")
            for rx in provenance_patterns():
                match = rx.search(text)
                if match:
                    errors.append(f"{path.relative_to(root)}: provenance or history '{match.group(0)}'")
            if re.search(r"\bherdr\b", text, re.IGNORECASE):
                errors.append(f"{path.relative_to(root)}: names the multiplexer (only engine/deliveryctl/window/ may)")

    engine = root / "engine" / "deliveryctl"
    for path in sorted(engine.rglob("*.py")) if engine.exists() else []:
        if "window" in path.parts or path.name in ("kit.py", "config.py", "roles.py"):
            continue
        if re.search(r"\bherdr\b", path.read_text(encoding="utf-8"), re.IGNORECASE):
            errors.append(f"{path.relative_to(root)}: names the multiplexer (only engine/deliveryctl/window/ may)")

    from . import roles
    cfg = parse_config({"repo_role": "impl", "commands": {"check": "just check"}}, root / "_kit")
    for role in roles.UNATTENDED:
        perms = roles.permissions(cfg, role, root / "_kit-wt", "s001")
        deny = set(perms["permissions"]["deny"])
        for tool in roles.DENY_TOOLS:
            if tool not in deny:
                errors.append(f"role file of {role}: '{tool}' is not denied")
        for must in ("Bash(git push)", "Bash(herdr *)", "Bash(deliveryctl merge *)"):
            if must not in deny:
                errors.append(f"role file of {role}: '{must}' is not denied")

    for manifest in (root / ".claude-plugin" / "plugin.json", root / ".claude-plugin" / "marketplace.json",
                     root / "hooks" / "hooks.json"):
        try:
            json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{manifest.relative_to(root)}: {exc}")

    engine_lines = sum(_lines(p) for p in engine.rglob("*.py")) if engine.exists() else 0
    prompt_lines = sum(_lines(p) for d in ("commands", "agents", "skills", "rules")
                       for p in (root / d).rglob("*.md")) if (root / "agents").exists() else 0
    template_lines = sum(_lines(p) for p in (root / "templates").rglob("*") if p.is_file()) \
        if (root / "templates").exists() else 0
    for name, value in (("engine", engine_lines), ("prompts", prompt_lines), ("templates", template_lines)):
        if value > BUDGET[name]:
            notes.append(f"budget: {name} {value} lines (signal above {BUDGET[name]})")
    notes.append(f"size: engine {engine_lines}, prompts {prompt_lines}, templates {template_lines} lines")
    return errors, notes


def main(args) -> int:
    errors, notes = lint(Path(args.path))
    for line in errors:
        print(f"- {line}")
    for line in notes:
        print(f"  {line}")
    print("kit: " + ("red" if errors else "green"))
    return EXIT_RED if errors else EXIT_OK
