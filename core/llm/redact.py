"""Strip contact details from text before it leaves for an AI provider (ADR-084).

The privacy page promises the AI providers never see a user's email, phone or
profile links. This is the one place that makes it true: `generate_json`, the
audio judge and the Live context turn all pass their text through `redact`.
The name stays (cover letters and answers read naturally with it).

Job-post URLs and source links stay too: the company brief cites them.
Only personal profile links (LinkedIn /in/, GitHub user pages) are removed.
"""
from __future__ import annotations

import re

_EMAIL = re.compile(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}")
# North American numbers: +1 (613) 555-0101, 613.555.0101, 6135550101 ...
_PHONE = re.compile(r"(?<![\w$])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?![\w%])")
_PROFILE = re.compile(
    r"(?:https?://)?(?:[\w-]+\.)?(?:linkedin\.com/in|github\.com)/[\w\-%./]+", re.I)

EMAIL_TOKEN = "[email]"
PHONE_TOKEN = "[phone]"
LINK_TOKEN = "[profile link]"


def redact(text: str) -> str:
    """`text` with emails, phone numbers and profile links replaced by tokens."""
    if not text:
        return text
    text = _PROFILE.sub(LINK_TOKEN, text)
    text = _EMAIL.sub(EMAIL_TOKEN, text)
    return _PHONE.sub(PHONE_TOKEN, text)
