"""Ports of the stories (CONTRACTS.md §3): <port_prefix><number on 3 digits>, or the next free
one, kept in the engine registry until the story is closed. Every command the engine runs for a
story gets it, as {port} and as DELIVERY_PORT."""

from __future__ import annotations

import socket

from .config import Config
from .core import ID_RX, file_lock, read_json, run_dir, write_json

REGISTRY = "ports.json"


def port(cfg: Config, scope: str) -> int:
    """Port of a story (or of another scope such as nightly-<day>), allocated once."""
    runs = run_dir(cfg.root)
    with file_lock(runs / "ports.lock"):
        ports = read_json(runs / REGISTRY, {})
        if scope in ports:
            return ports[scope]
        number = int(scope[1:]) % 1000 if ID_RX.match(scope) else 999
        value = int(f"{cfg.port_prefix}{number:03d}")
        taken = set(ports.values())
        while value in taken or listening(value):
            value += 1
        ports[scope] = value
        write_json(runs / REGISTRY, ports)
    return value


def release(cfg: Config, scope: str) -> None:
    runs = run_dir(cfg.root)
    with file_lock(runs / "ports.lock"):
        ports = read_json(runs / REGISTRY, {})
        if ports.pop(scope, None) is not None:
            write_json(runs / REGISTRY, ports)


def listening(value: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", value)) == 0
