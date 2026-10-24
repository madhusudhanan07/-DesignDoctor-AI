"""URL normalization, sanitization, and safety verification for DesignDoctor AI.

Prevents duplicated schemes (e.g. https://https://w3.org), validates public hostnames,
and blocks internal/private IP ranges.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse

_BLOCKED_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

# Regex pattern to match one or more repeated schemes (e.g. https://, http://, https://https://)
_SCHEME_PREFIX_RE = re.compile(r"^(?:https?://)+", re.IGNORECASE)


def normalize_url(raw_url: str, check_dns: bool = True) -> tuple[bool, str, str]:
    """Normalize and validate a URL for auditing.

    Args:
        raw_url: The input URL or domain string.
        check_dns: Whether to perform DNS resolution and IP address safety checks.

    Returns:
        (is_valid, normalized_url, error_message)
    """
    if not raw_url or not isinstance(raw_url, str):
        return False, "", "URL cannot be empty."

    url = raw_url.strip()
    if not url:
        return False, "", "URL cannot be empty."

    # Remove any duplicate schemes at the beginning (e.g., https://https:// or http://https://)
    cleaned = _SCHEME_PREFIX_RE.sub("", url).strip()

    # Also handle accidental trailing slashes or colons in scheme position like "https:w3.org"
    cleaned = re.sub(r"^(?:https?:/*)+", "", cleaned, flags=re.IGNORECASE).strip()

    if not cleaned:
        return False, "", "No domain or hostname provided in URL."

    # Reconstruct with a clean standard https:// scheme
    normalized = f"https://{cleaned}"

    # Parse and validate structure
    try:
        parsed = urllib.parse.urlparse(normalized)
    except Exception as e:
        return False, "", f"Could not parse URL: {e}"

    host = parsed.hostname
    if not host:
        return False, "", "Missing valid hostname in URL."

    # Validate hostname syntax
    if " " in host or "\t" in host or "\n" in host:
        return False, "", "Hostname contains invalid whitespace characters."

    # Check for basic domain validity (e.g., requires at least a dot unless localhost, which is blocked)
    if "." not in host and host.lower() not in ("localhost", "0.0.0.0"):
        return False, "", f"Invalid domain name: '{host}' does not have a top-level domain."

    # Block localhost and private addresses
    if host.lower() in ("localhost", "0.0.0.0", "127.0.0.1", "::1"):
        return False, "", "Private and localhost addresses are blocked for security."

    if not check_dns:
        return True, normalized, ""

    # Resolve IP and check against blocked networks
    try:
        addrs = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # If hostname resolution fails offline or domain doesn't exist
        return False, "", f"Could not resolve domain: '{host}'"

    for info in addrs:
        try:
            addr = ipaddress.ip_address(info[4][0])
            for net in _BLOCKED_NETS:
                if addr in net:
                    return False, "", f"Private or internal IP address is blocked: {addr}"
        except ValueError:
            pass

    return True, normalized, ""


def is_valid_url(raw_url: str, check_dns: bool = False) -> bool:
    """Return True if the URL is valid and public, False otherwise."""
    valid, _, _ = normalize_url(raw_url, check_dns=check_dns)
    return valid


def clean_url(raw_url: str) -> str:
    """Strip duplicate schemes and return the clean normalized URL, or empty string if invalid."""
    valid, norm, _ = normalize_url(raw_url, check_dns=False)
    return norm if valid else ""
