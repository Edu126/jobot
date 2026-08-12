"""Version metadata read from the VERSION file at repo root.

Kept as a tiny module so the value is a single source of truth — CI, the
in-app updater, and the packaging script all import from here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def current() -> str:
    """The version string from VERSION file. Falls back to '0.0.0-dev' if
    the file is missing (repo-dev checkout without VERSION)."""
    try:
        return _VERSION_FILE.read_text(encoding="utf-8").strip() or "0.0.0-dev"
    except OSError:
        return "0.0.0-dev"


def parse(v: str) -> tuple[int, int, int]:
    """Parse `v0.3.0`, `0.3.0`, `0.3.0-dev` into a comparable tuple.

    Non-numeric suffixes (`-dev`, `-rc1`) are stripped and treated as the
    same major.minor.patch. Missing parts default to 0. Malformed inputs
    return (0, 0, 0) so upgrade prompts don't fire on garbage.
    """
    v = (v or "").strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = v.split(".")[:3]
    out = [0, 0, 0]
    for i, p in enumerate(parts):
        try:
            out[i] = int(p)
        except ValueError:
            pass
    return (out[0], out[1], out[2])


def is_newer(remote: str, local: Optional[str] = None) -> bool:
    """True when `remote` is a strictly higher version than `local`
    (defaults to the current VERSION)."""
    if local is None:
        local = current()
    return parse(remote) > parse(local)
