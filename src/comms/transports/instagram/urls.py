"""A publish URL (proposed A49, section 6; D-I6): checked syntactically and passed to Meta,
which fetches it. comms never fetches it, so the check is about what may leave comms: an
``https`` URL to a public DNS name, no userinfo, no IP literal in any spelling, no
``localhost`` or private-use name, no port but 443, no whitespace, at most 2,048 characters.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

__all__ = ["URL_MAX", "public_url"]

URL_MAX = 2048
_LABEL = re.compile(r"\A(?!-)[a-z0-9-]{1,63}(?<!-)\Z")
_TLD = re.compile(r"\A(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})\Z")
_PRIVATE_SUFFIXES = ("localhost", "local", "internal", "home.arpa", "lan", "intranet", "corp")
_VISIBLE = re.compile(r"\A[\x21-\x7e]+\Z")  # printable ASCII, no space


def public_url(value: object) -> str:
    """``value`` itself when it may be handed to Meta; ``ValueError`` otherwise."""
    if not isinstance(value, str) or not 1 <= len(value) <= URL_MAX or not _VISIBLE.match(value):
        raise ValueError("url refused")
    parts = urlsplit(value)
    if parts.scheme != "https" or "@" in parts.netloc:
        raise ValueError("url refused")
    try:
        port = parts.port
    except ValueError:
        raise ValueError("url refused") from None
    if port not in (None, 443):
        raise ValueError("url refused")
    host = (parts.hostname or "").rstrip(".")
    if not host or host != host.lower() or _ip_literal(host):
        raise ValueError("url refused")
    labels = host.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        raise ValueError("url refused")
    if not _TLD.match(labels[-1]):
        raise ValueError("url refused")
    if any(host == s or host.endswith("." + s) for s in _PRIVATE_SUFFIXES):
        raise ValueError("url refused")
    return value


def _ip_literal(host: str) -> bool:
    """An address in any spelling a resolver accepts: dotted, short, hex, octal or integer."""
    if host.startswith("["):
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    labels = host.split(".")
    return len(labels) <= 4 and all(re.fullmatch(r"(?:0x[0-9a-f]*|[0-9]+)", p) for p in labels)
