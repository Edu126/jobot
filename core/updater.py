"""In-app update checker + downloader against GitHub Releases.

Flow:
    1. `check()` hits GitHub API, returns { current, latest, has_update, url }
    2. `download(url)` streams the release zip to dist/pending-update.zip
    3. User double-clicks `Update Jobot.command` (ships in the zip) to apply

We deliberately don't try to install the update in-process — that would
require killing our own uvicorn worker + relaunching, which is fragile.
The Update.command handles the extract/rsync/restart lifecycle where an
external supervisor can supervise cleanly.
"""
from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from core.version import current as current_version, is_newer


# Where to pull release metadata from. Override with env vars for forks.
GH_OWNER = os.environ.get("JOBOT_GH_OWNER", "Edu126")
GH_REPO = os.environ.get("JOBOT_GH_REPO", "jobot")

API_URL = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/releases/latest"

# Where downloaded update zips land — same folder Update.command reads from.
APP_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = APP_ROOT / "dist"
PENDING_ZIP = DIST_DIR / "pending-update.zip"

# Only hosts we'll accept in download() — bounds the trust model. Even if a
# poisoned env var swaps GH_OWNER/GH_REPO, the download can't be redirected
# to attacker infrastructure that then gets extracted by Update.command.
_ALLOWED_DOWNLOAD_HOSTS = frozenset({
    "api.github.com",
    "github.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
})


class UpdateDownloadError(RuntimeError):
    """Raised when the download URL fails validation or the fetch errors out."""


@dataclass
class UpdateStatus:
    current: str
    latest: Optional[str]
    has_update: bool
    download_url: Optional[str]      # URL of the release asset zip
    release_notes: str
    error: Optional[str]             # populated if API call failed
    pending_downloaded: bool         # True if pending-update.zip already exists

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self.current,
            "latest": self.latest,
            "has_update": self.has_update,
            "download_url": self.download_url,
            "release_notes": self.release_notes,
            "error": self.error,
            "pending_downloaded": self.pending_downloaded,
        }


def check() -> UpdateStatus:
    """Query GitHub for the latest release. Handles 404 (no releases yet)
    and network errors gracefully — we never want a broken updater to break
    the profile page."""
    cur = current_version()
    pending = PENDING_ZIP.exists()

    try:
        req = urllib.request.Request(
            API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"jobot/{cur}",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — network + parse errors all bucket here
        return UpdateStatus(
            current=cur, latest=None, has_update=False,
            download_url=None, release_notes="",
            error=f"Couldn't reach GitHub: {exc}",
            pending_downloaded=pending,
        )

    latest_tag = str(data.get("tag_name", "")).lstrip("vV")
    notes = str(data.get("body") or "").strip()

    # Find the first .zip asset in the release
    asset_url: Optional[str] = None
    for asset in data.get("assets") or []:
        name = str(asset.get("name", ""))
        if name.endswith(".zip"):
            asset_url = asset.get("browser_download_url")
            break

    return UpdateStatus(
        current=cur,
        latest=latest_tag or None,
        has_update=bool(latest_tag and asset_url and is_newer(latest_tag, cur)),
        download_url=asset_url,
        release_notes=notes[:1500],   # cap so the modal isn't a wall of text
        error=None,
        pending_downloaded=pending,
    )


def download(url: str) -> Path:
    """Stream the release zip to dist/pending-update.zip. Overwrites any
    previous pending download. Returns the path on success; raises on error.

    Enforces an https + host allowlist so a poisoned check() response can't
    trick us into fetching arbitrary content that Update.command would then
    extract onto disk.
    """
    parsed = urlparse(url or "")
    if parsed.scheme != "https":
        raise UpdateDownloadError(
            f"Update URL must be https, got '{parsed.scheme}://'"
        )
    if parsed.hostname not in _ALLOWED_DOWNLOAD_HOSTS:
        raise UpdateDownloadError(
            f"Update host '{parsed.hostname}' not in the allowlist. "
            "Only GitHub-served asset URLs are accepted."
        )

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PENDING_ZIP.with_suffix(".zip.tmp")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"jobot/{current_version()}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        with open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)

    tmp.replace(PENDING_ZIP)   # atomic swap
    return PENDING_ZIP


def clear_pending() -> None:
    """Remove pending-update.zip if it exists — used by Update.command after
    successfully applying, or by a 'Cancel update' UI action."""
    try:
        PENDING_ZIP.unlink()
    except FileNotFoundError:
        pass
