"""Experience journal: JSON events in PostgreSQL, read by the human only (CONTRACTS.md §13).

Writes never fail a command: when the database is unreachable, the event waits in a local
queue that `journal flush` empties later. Validation is fail-open: a malformed event is kept
and marked invalid.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from . import VERSION, config
from .core import (EXIT_REFUSED, EXIT_TOOL, append_jsonl, eprint, fail, file_lock, is_role_session, now_iso,
                   state_home)

SCHEMA = "delivery-event/1"
CATEGORIES = ("stall", "refusal", "resume", "compact", "verify-exhausted", "review-exhausted",
              "spec-gap", "night-anomalies", "summary", "note", "other")
SOURCES = ("engine", "human", "agent")
BATCH = 200
DDL = ("CREATE TABLE IF NOT EXISTS delivery_journal (id bigserial PRIMARY KEY, "
       "recorded_at timestamptz NOT NULL DEFAULT now(), event jsonb NOT NULL);")
SETUP = """Journal d'expérience — mise en place locale (une fois par machine)

  docker run -d --name delivery-journal --restart unless-stopped \\
    -e POSTGRES_USER=delivery -e POSTGRES_PASSWORD=delivery -e POSTGRES_DB=delivery \\
    -p 127.0.0.1:55432:5432 -v delivery-journal:/var/lib/postgresql/data postgres:17

Puis dans ~/.config/delivery-method/machine.toml :

  journal_dsn = "postgresql://delivery:delivery@127.0.0.1:55432/delivery"

La table est créée au premier envoi. Le volume nommé survit aux redémarrages.
"""


def queue_path() -> Path:
    return state_home() / "journal-queue.jsonl"


def _queue_lock() -> Path:
    return queue_path().with_suffix(".lock")


def event(repo: str, category: str, text: str, story: str = "", role: str = "engine",
          source: str = "engine", evidence: str = "") -> dict:
    ev = {"schema": SCHEMA, "ts": now_iso(), "method_version": VERSION, "repo": repo,
          "story": story, "role": role, "source": source, "category": category,
          "text": text, "evidence": evidence}
    problems = []
    if category not in CATEGORIES:
        problems.append(f"unknown category '{category}'")
    if source not in SOURCES:
        problems.append(f"unknown source '{source}'")
    if not text.strip():
        problems.append("empty text")
    if problems:
        ev["invalid"] = problems
    return ev


def psql_env(dsn: str, connect_timeout: int = 5) -> dict:
    """libpq environment for a DSN, so that the password never shows on a command line:
    a URL (postgresql://user:password@host:port/database?sslmode=…) or 'key=value' words."""
    env = {"PGCONNECT_TIMEOUT": str(connect_timeout)}
    names = {"host": "PGHOST", "hostaddr": "PGHOSTADDR", "port": "PGPORT", "user": "PGUSER",
             "password": "PGPASSWORD", "dbname": "PGDATABASE", "sslmode": "PGSSLMODE",
             "application_name": "PGAPPNAME", "connect_timeout": "PGCONNECT_TIMEOUT",
             "options": "PGOPTIONS", "service": "PGSERVICE", "target_session_attrs": "PGTARGETSESSIONATTRS"}
    dsn = dsn.strip()
    try:
        if dsn.startswith(("postgresql://", "postgres://")):
            url = urlsplit(dsn)
            netloc = url.netloc.rpartition("@")[2]
            host = netloc.rsplit(":", 1)[0] if not netloc.endswith("]") and ":" in netloc else netloc
            values = {"user": unquote(url.username or ""), "password": unquote(url.password or ""),
                      "host": unquote(host.strip("[]")), "port": str(url.port or ""),
                      "dbname": unquote(url.path.lstrip("/"))}
            values.update(parse_qsl(url.query))
        else:
            values = dict(word.split("=", 1) for word in shlex.split(dsn) if "=" in word)
    except ValueError:
        values = {}
    env.update({names[k]: v for k, v in values.items() if k in names and v})
    return env


def _without_nul(value):
    if isinstance(value, str):
        return value.replace("\0", "")
    if isinstance(value, dict):
        return {k: _without_nul(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_without_nul(v) for v in value]
    return value


def _literal(ev: dict) -> str:
    """The event as a SQL string literal: JSON on one line, quotes doubled, without NUL
    characters (jsonb refuses them)."""
    text = json.dumps(_without_nul(ev), ensure_ascii=False)
    return "'" + text.replace("'", "''") + "'"


def _insert(dsn: str, events: list[dict], timeout: int) -> str:
    """Insert events in one transaction; returns '' on success, else the reason."""
    if not dsn:
        return "journal_dsn is empty"
    if not shutil.which("psql"):
        return "psql is not installed"
    if not events:
        return ""
    script = "\n".join(["SET standard_conforming_strings = on;", DDL] + [
        f"INSERT INTO delivery_journal(event) VALUES ({_literal(ev)}::jsonb);" for ev in events]) + "\n"
    env = dict(os.environ, **psql_env(dsn, min(timeout, 10)))
    try:
        proc = subprocess.run(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "--single-transaction", "-f", "-"],
                              input=script, text=True, capture_output=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout).strip() or f"psql exit {proc.returncode}"
    return ""


def record(ev: dict) -> None:
    """Store an event; fall back to the local queue. Never raises; waits 5 s at most for the
    database, so that a hook stays within its time."""
    try:
        dsn = config.machine().get("journal_dsn", "")
    except Exception:
        dsn = ""
    if dsn and not _insert(dsn, [ev], timeout=5):
        return
    try:
        with file_lock(_queue_lock()):
            append_jsonl(queue_path(), ev)
    except OSError:
        pass


def flush() -> tuple[int, int]:
    """Send queued events by batches of BATCH, one transaction each; the queue is rewritten
    after each batch sent, keeping what was appended meanwhile. Returns (sent, still queued)."""
    path = queue_path()
    with file_lock(path.with_name("journal-flush.lock")):
        with file_lock(_queue_lock()):
            if not path.exists():
                return 0, 0
            raw = path.read_bytes()
        lines = [line for line in raw.decode("utf-8", errors="replace").splitlines() if line.strip()]
        events = []
        for line in lines:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"schema": SCHEMA, "invalid": ["unreadable queue line"], "text": line})
        dsn = config.machine().get("journal_dsn", "")
        sent, own = 0, len(raw)
        while sent < len(events):
            batch = events[sent:sent + BATCH]
            error = _insert(dsn, batch, timeout=60)
            if error:
                eprint(f"journal flush: {' '.join(error.split())[:300]}")
                break
            sent += len(batch)
            kept = "".join(line + "\n" for line in lines[sent:]).encode("utf-8")
            with file_lock(_queue_lock()):
                appended = path.read_bytes()[own:] if path.exists() else b""
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(kept + appended)
                os.replace(tmp, path)
            own = len(kept)
        with file_lock(_queue_lock()):
            if path.exists() and not path.read_bytes().strip():
                path.unlink()
        return sent, len(events) - sent


def _in_equipped_repo() -> bool:
    here = Path.cwd().resolve()
    return any((p / "delivery.toml").exists() for p in (here, *here.parents))


def report(limit: int = 50) -> str:
    """Latest events, for the human, outside any role session and any equipped repository."""
    if is_role_session() or _in_equipped_repo():
        fail(EXIT_REFUSED, "the journal is read by the human only, outside role sessions and "
                           "outside equipped repositories")
    dsn = config.machine().get("journal_dsn", "")
    lines = []
    if dsn:
        if not shutil.which("psql"):
            fail(EXIT_TOOL, "journal_dsn is set but psql is not installed")
        query = ("SELECT recorded_at::timestamp(0), event->>'repo', event->>'story', event->>'category', "
                 f"event->>'text' FROM delivery_journal ORDER BY id DESC LIMIT {int(limit)};")
        proc = subprocess.run(["psql", "-X", "-q", "-A", "-F", " | ", "-t", "-c", query],
                              text=True, capture_output=True, timeout=20, env=dict(os.environ, **psql_env(dsn)))
        if proc.returncode != 0:
            fail(EXIT_TOOL, f"journal unreachable: {proc.stderr.strip()}")
        lines += [line for line in proc.stdout.splitlines() if line.strip()]
    path = queue_path()
    if path.exists():
        queued = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if queued and dsn:
            lines.append(f"({len(queued)} événement(s) en attente d'envoi : deliveryctl journal flush)")
        for ev in queued[-int(limit):] if not dsn else []:
            lines.append(" | ".join(str(ev.get(k, "")) for k in ("ts", "repo", "story", "category", "text")))
    return "\n".join(lines) or "Journal vide."
