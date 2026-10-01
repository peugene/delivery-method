"""Project settings (delivery.toml) and machine settings (machine.toml), CONTRACTS.md §3-§4."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .core import EXIT_ERROR, EXIT_PRECONDITION, config_home, fail

PROJECT_FILE = "delivery.toml"

RISKS = ("authz", "data-write", "file-upload", "data-leak", "migration", "api-contract",
         "new-screen", "scheduling", "realtime", "dependency")
REINFORCED_CHECKS = ("bite", "adversarial-review")

LEVER_DEFAULTS = {
    "review_loops": 2,
    "verify_attempts": 3,
    "short_path_max_lines": 50,
    "stall_minutes": 20,
    "reinforced_risks": {
        "authz": ["bite", "adversarial-review"],
        "data-write": ["adversarial-review"],
        "file-upload": ["adversarial-review"],
        "data-leak": ["adversarial-review"],
    },
    "doc_globs": ["docs/**", "*.md"],
    "max_order_lines": 60,
}

# key: (type, allowed values or None, default)
TOP_SCHEMA = {
    "repo_role": (str, ("single", "spec", "impl"), None),
    "content_language": (str, None, "en"),
    "release_stage": (str, ("pre-release", "released"), "pre-release"),
    "external_contracts": (list, None, []),
    "forge": (str, ("github", "gitlab"), "github"),
    "integration": (str, ("human", "ai"), "human"),
    "implementer": (str, ("cloud", "local"), ""),      # '' = by forge: cloud with github, local with gitlab
    "max_in_flight": (int, None, 3),
    "agent_prefix": (str, None, ""),
    "port_prefix": (int, None, 31),
    "commands": (dict, None, {}),
    "permissions": (dict, None, {}),
    "levers": (dict, None, {}),
}
COMMAND_KEYS = ("check", "test", "acceptance", "serve")
PERMISSION_KEYS = ("extra_allow",)

MACHINE_DEFAULTS = {
    "window": "auto",
    "notify_cmd": "",
    "notify_story_end": False,
    "journal_dsn": "",
    "plugin_dir": "",
}
MACHINE_VALUES = {"window": ("auto", "herdr", "terminal")}


@dataclass
class Config:
    root: Path
    repo_role: str
    content_language: str
    release_stage: str
    external_contracts: list
    forge: str
    integration: str
    max_in_flight: int
    agent_prefix: str
    port_prefix: int
    commands: dict
    extra_allow: list
    levers: dict = field(default_factory=dict)
    implementer: str = "local"

    def lever(self, name: str):
        return self.levers[name]

    @property
    def risks(self) -> tuple:
        """Default risks plus the ones a project declares as keys of reinforced_risks."""
        return tuple(dict.fromkeys(list(RISKS) + list(self.levers["reinforced_risks"])))

    def command(self, name: str, **subst) -> str | None:
        template = self.commands.get(name)
        if not template:
            return None
        text = template
        for key, value in subst.items():
            text = text.replace("{" + key + "}", str(value))
        return text


def _typecheck(value, expected, where: str):
    if expected is int and (isinstance(value, bool) or not isinstance(value, int)):
        fail(EXIT_ERROR, f"{where}: expected an integer, got {value!r}")
    if expected is not int and not isinstance(value, expected):
        fail(EXIT_ERROR, f"{where}: expected {expected.__name__}, got {value!r}")


def parse(data: dict, root: Path, source: str = PROJECT_FILE) -> Config:
    for key in data:
        if key not in TOP_SCHEMA:
            fail(EXIT_ERROR, f"{source}: unknown key '{key}'")
    values = {}
    for key, (typ, allowed, default) in TOP_SCHEMA.items():
        if key not in data:
            if default is None:
                fail(EXIT_ERROR, f"{source}: missing key '{key}'")
            values[key] = default.copy() if isinstance(default, (list, dict)) else default
            continue
        value = data[key]
        _typecheck(value, typ, f"{source}: {key}")
        if allowed and value not in allowed:
            fail(EXIT_ERROR, f"{source}: {key} must be one of {', '.join(allowed)}, got '{value}'")
        values[key] = value
    if values["max_in_flight"] < 1:
        fail(EXIT_ERROR, f"{source}: max_in_flight must be at least 1")
    if not 10 <= values["port_prefix"] <= 64:
        fail(EXIT_ERROR, f"{source}: port_prefix must be between 10 and 64")
    for key, value in values["commands"].items():
        if key not in COMMAND_KEYS:
            fail(EXIT_ERROR, f"{source}: unknown key 'commands.{key}'")
        _typecheck(value, str, f"{source}: commands.{key}")
    for key in values["permissions"]:
        if key not in PERMISSION_KEYS:
            fail(EXIT_ERROR, f"{source}: unknown key 'permissions.{key}'")
    extra = values["permissions"].get("extra_allow", [])
    _typecheck(extra, list, f"{source}: permissions.extra_allow")
    levers = {k: (v.copy() if isinstance(v, (list, dict)) else v) for k, v in LEVER_DEFAULTS.items()}
    for key, value in values["levers"].items():
        if key not in LEVER_DEFAULTS:
            fail(EXIT_ERROR, f"{source}: unknown lever '{key}'")
        default = LEVER_DEFAULTS[key]
        _typecheck(value, type(default), f"{source}: levers.{key}")
        if key == "reinforced_risks":      # per risk: a written key completes or replaces its default
            value = {**levers[key], **value}
        levers[key] = value
    for risk, checks in levers["reinforced_risks"].items():
        if not isinstance(checks, list):
            fail(EXIT_ERROR, f"{source}: levers.reinforced_risks.{risk}: expected a list")
        for check in checks:
            if check not in REINFORCED_CHECKS:
                fail(EXIT_ERROR, f"{source}: levers.reinforced_risks.{risk}: unknown check '{check}'")
    if not values["implementer"]:
        values["implementer"] = "cloud" if values["forge"] == "github" else "local"
    elif values["implementer"] == "cloud" and values["forge"] != "github":
        fail(EXIT_ERROR, f"{source}: implementer = cloud needs forge = github "
                         "(a cloud session pushes to GitHub only)")
    if not values["agent_prefix"]:
        values["agent_prefix"] = "".join(w[0] for w in root.name.split("-") if w)[:4] or "dm"
    return Config(
        root=root,
        repo_role=values["repo_role"],
        content_language=values["content_language"],
        release_stage=values["release_stage"],
        external_contracts=values["external_contracts"],
        forge=values["forge"],
        integration=values["integration"],
        max_in_flight=values["max_in_flight"],
        agent_prefix=values["agent_prefix"],
        port_prefix=values["port_prefix"],
        commands=values["commands"],
        extra_allow=extra,
        levers=levers,
        implementer=values["implementer"],
    )


def load(root: Path) -> Config:
    path = Path(root) / PROJECT_FILE
    if not path.exists():
        fail(EXIT_PRECONDITION, f"{path} not found: run 'deliveryctl init' first")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        fail(EXIT_ERROR, f"{path}: {exc}")
    return parse(data, Path(root), str(path))


def machine_path() -> Path:
    return config_home() / "machine.toml"


def machine() -> dict:
    """Machine settings with defaults; unknown keys are refused like in delivery.toml."""
    out = dict(MACHINE_DEFAULTS)
    path = machine_path()
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            fail(EXIT_ERROR, f"{path}: {exc}")
        for key, value in data.items():
            if key not in MACHINE_DEFAULTS:
                fail(EXIT_ERROR, f"{path}: unknown key '{key}'")
            _typecheck(value, type(MACHINE_DEFAULTS[key]), f"{path}: {key}")
            if key in MACHINE_VALUES and value not in MACHINE_VALUES[key]:
                fail(EXIT_ERROR, f"{path}: {key} must be one of {', '.join(MACHINE_VALUES[key])}")
            out[key] = value
    env_window = os.environ.get("DELIVERY_WINDOW")
    if env_window in MACHINE_VALUES["window"]:
        out["window"] = env_window
    return out
