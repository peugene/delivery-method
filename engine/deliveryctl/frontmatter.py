"""Flat YAML frontmatter subset and markdown sections.

Frontmatter lines are `key: value`; a value is a scalar (string, int, bool, empty), an inline
list `[a, b]` or an inline map `{k: v, k2: [a]}`. Comments start with ` #`. Anything else
(indentation, block lists, anchors) is rejected, so every file parses the same way with the
standard library only.
"""

from __future__ import annotations

import re
from pathlib import Path

from .core import EXIT_RED, DeliveryError

KEY_RX = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s+(.*))?$")
INT_RX = re.compile(r"^-?[0-9]+$")
HEADING_RX = re.compile(r"^(#{1,6}) (.+?)\s*$")


class FrontmatterError(DeliveryError):
    def __init__(self, message: str):
        super().__init__(EXIT_RED, message)


def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


class _Parser:
    def __init__(self, text: str):
        self.s, self.i = text, 0

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else ""

    def value(self, nested: bool):
        self.ws()
        ch = self.peek()
        if ch == "":
            return None
        if ch == "[":
            return self.seq()
        if ch == "{":
            return self.mapping()
        if ch in ("'", '"'):
            return self.quoted()
        return self.bare(nested)

    def seq(self):
        self.i += 1
        items = []
        self.ws()
        if self.peek() == "]":
            self.i += 1
            return items
        while True:
            items.append(self.value(nested=True))
            self.ws()
            ch = self.peek()
            self.i += 1
            if ch == "]":
                return items
            if ch != ",":
                raise ValueError("expected ',' or ']' in list")

    def mapping(self):
        self.i += 1
        out = {}
        self.ws()
        if self.peek() == "}":
            self.i += 1
            return out
        while True:
            self.ws()
            start = self.i
            while self.peek() not in (":", ""):
                self.i += 1
            key = self.s[start:self.i].strip()
            if not key or self.peek() != ":":
                raise ValueError("expected 'key:' in map")
            self.i += 1
            out[key] = self.value(nested=True)
            self.ws()
            ch = self.peek()
            self.i += 1
            if ch == "}":
                return out
            if ch != ",":
                raise ValueError("expected ',' or '}' in map")

    def quoted(self):
        quote = self.s[self.i]
        self.i += 1
        start = self.i
        while self.peek() not in (quote, ""):
            self.i += 1
        if self.peek() != quote:
            raise ValueError("unterminated string")
        text = self.s[start:self.i]
        self.i += 1
        return text

    def bare(self, nested: bool):
        start = self.i
        stops = ",]}" if nested else ""
        while self.peek() and self.peek() not in stops:
            self.i += 1
        return scalar(self.s[start:self.i].strip())


def scalar(raw: str):
    if raw == "" or raw in ("null", "~"):
        return None
    if raw in ("true", "false"):
        return raw == "true"
    if INT_RX.match(raw):
        return int(raw)
    return raw


def parse_value(text: str):
    parser = _Parser(text)
    value = parser.value(nested=False)
    parser.ws()
    if parser.i != len(parser.s):
        raise ValueError(f"unexpected text after value: {parser.s[parser.i:]!r}")
    return value


def split(text: str, source: str = "<text>") -> tuple[dict, str]:
    """Return (frontmatter dict, body). A file without frontmatter yields ({}, text)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    data: dict = {}
    for n, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            body = "\n".join(lines[n:])
            return data, body + ("\n" if text.endswith("\n") and body else "")
        clean = _strip_comment(line)
        if not clean.strip():
            continue
        match = KEY_RX.match(clean)
        if not match or line[:1] in (" ", "\t"):
            raise FrontmatterError(f"{source}:{n}: unsupported frontmatter line: {line!r}")
        key, raw = match.group(1), match.group(2) or ""
        if key in data:
            raise FrontmatterError(f"{source}:{n}: duplicate key '{key}'")
        try:
            data[key] = parse_value(raw)
        except ValueError as exc:
            raise FrontmatterError(f"{source}:{n}: {exc}") from None
    raise FrontmatterError(f"{source}: frontmatter is not closed by '---'")


def load(path: Path) -> tuple[dict, str]:
    return split(Path(path).read_text(encoding="utf-8"), str(path))


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(format_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {format_value(v)}" for k, v in value.items()) + "}"
    text = str(value)
    if text == "" or any(ch in text for ch in ",[]{}#:") or text != text.strip():
        return '"' + text.replace('"', "'") + '"'
    return text


def set_key(text: str, key: str, value) -> str:
    """Rewrite one frontmatter key in place, keeping comments and the other lines."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("no frontmatter to update")
    for n in range(1, len(lines)):
        line = lines[n]
        if line.strip() == "---":
            lines.insert(n, f"{key}: {format_value(value)}\n")
            return "".join(lines)
        match = KEY_RX.match(_strip_comment(line))
        if match and match.group(1) == key:
            comment = ""
            stripped = _strip_comment(line.rstrip("\n"))
            rest = line.rstrip("\n")[len(stripped):]
            if rest.strip().startswith("#"):
                comment = "  " + rest.strip()
            lines[n] = f"{key}: {format_value(value)}{comment}\n"
            return "".join(lines)
    raise FrontmatterError("frontmatter is not closed by '---'")


def sections(body: str, level: int = 2) -> list[tuple[str, str]]:
    """Split a markdown body into (heading, content) at the given heading level.
    Text before the first heading is returned under the heading ''."""
    out: list[tuple[str, list[str]]] = [("", [])]
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        match = None if in_fence else HEADING_RX.match(line)
        if match and len(match.group(1)) == level:
            out.append((match.group(2).strip(), []))
        else:
            out[-1][1].append(line)
    return [(h, "\n".join(c).strip("\n")) for h, c in out]


def section_map(body: str, level: int = 2) -> dict[str, str]:
    """Headings are matched on their first words: '## Oracle' and '## Oracle (frozen)' both
    map to 'Oracle' via section_get."""
    return {h: c for h, c in sections(body, level) if h}


def section_get(body: str, name: str, level: int = 2) -> str | None:
    for heading, content in sections(body, level):
        if heading == name or heading.startswith(name + " ") or heading.startswith(name + " —"):
            return content
    return None


def meaningful(content: str | None) -> bool:
    """True when a section holds more than placeholders, comments or blank lines."""
    if not content:
        return False
    for line in content.splitlines():
        text = line.strip()
        if not text or text.startswith("<!--") or (text.startswith("<") and text.endswith(">")):
            continue
        if text in ("-", "*", "…", "...", "TBD", "TODO"):
            continue
        return True
    return False
