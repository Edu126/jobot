"""The data map (docs/governance/data_map.yaml) must list every outside
service the code talks to (ADR-084). Scans core/ and ui_web/ for https hosts
and network SDK imports; anything not matched by a service's `detect` fails.

Runs without pytest:
    .venv/bin/python tests/test_data_map.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
# Hosts in strings that are documentation or schema links, never called.
NOT_CALLED = {"schema.org", "jsonresume.org", "docs.oracle.com", "developers.greenhouse.io",
              "developers.google.com", "hire.lever.co"}
HOST = re.compile(r"https?://([A-Za-z0-9.-]+\.[a-z]{2,})")
SDK = re.compile(r"^\s*(?:from|import) (google\.genai|google import genai|jobspy|resend|supabase|openai|anthropic)\b", re.M)


def main() -> int:
    data = yaml.safe_load((ROOT / "docs/governance/data_map.yaml").read_text())
    detects = [d for s in data["services"] for d in s.get("detect", [])]
    for s in data["services"]:
        for k in ("name", "user_data", "why", "where"):
            assert s.get(k), f"service {s.get('name')!r} is missing {k}"

    found: dict[str, str] = {}
    for py in list((ROOT / "core").rglob("*.py")) + list((ROOT / "ui_web").rglob("*.py")):
        text = py.read_text(errors="ignore")
        for h in HOST.findall(text):
            if h not in NOT_CALLED:
                found.setdefault(h, str(py.relative_to(ROOT)))
        for m in SDK.findall(text):
            found.setdefault(m, str(py.relative_to(ROOT)))

    missing = {k: v for k, v in found.items() if not any(d in k or k in d for d in detects)}
    assert not missing, ("Outside services used in code but missing from docs/governance/data_map.yaml "
                         f"(add them, then update the privacy page): {missing}")
    print(f"OK — data map covers {len(found)} outside hosts/SDKs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
