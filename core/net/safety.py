"""SSRF guard shared by every outbound-fetch caller.

Any code path that fetches a URL derived from user input must call
`is_safe_public_ip(host)` before the request goes out — otherwise a
malicious paste can point us at cloud metadata (169.254.169.254),
localhost admin panels, or private-network hosts and exfiltrate the
response via the LLM's output or the UI.

Kept in its own module so both the LLM fallback (`from_url.py`) and the
per-ATS adapters (`core/jobs/ats/*`) import the same implementation.
"""
from __future__ import annotations

import ipaddress
import socket


def is_safe_public_ip(host: str) -> bool:
    """False if `host` resolves to any private/loopback/link-local/
    multicast/reserved IP. `host` may be a hostname or a literal IP.

    Returns False on DNS-resolution failures too — refuse-by-default is
    the safer choice for a security check."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        raw_ip = info[4][0]
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        ):
            return False
    return True
