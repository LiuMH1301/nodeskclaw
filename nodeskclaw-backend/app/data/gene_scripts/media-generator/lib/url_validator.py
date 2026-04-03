"""
URL allowlist factory for SSRF protection.

Usage:
    validator = create_url_validator(providers)
    validator.require_valid_url("https://api.openai.com/v1/images")

Adding a provider: No changes here. The new provider module declares its
allowed_domains, and server.py passes all providers to this factory.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlparse


def create_url_validator(providers: list[dict], local_media_dir: str) -> "UrlValidator":
    """Build validator from aggregated provider configs."""
    allowed_domains: list[str] = []
    for p in providers:
        for domain in p.get("allowed_domains", []):
            allowed_domains.append(domain)

    resolved_media_dir = str(Path(local_media_dir).resolve())

    return UrlValidator(allowed_domains, resolved_media_dir)


class UrlValidator:
    """Immutable URL validator. Created once at startup, never mutated."""

    def __init__(self, allowed_domains: list[str], media_dir: str) -> None:
        self._allowed_domains = tuple(allowed_domains)
        self._media_dir = media_dir

    def _matches_domain(self, hostname: str) -> bool:
        """Check hostname against allowlist with subdomain suffix matching."""
        for d in self._allowed_domains:
            if hostname == d or hostname.endswith(f".{d}"):
                return True
        return False

    @staticmethod
    def _is_ip_literal(hostname: str) -> bool:
        """Return True if hostname is an IP address literal (v4 or v6)."""
        try:
            ipaddress.ip_address(hostname.strip("[]"))
            return True
        except ValueError:
            return False

    @staticmethod
    def _resolves_to_private(hostname: str) -> bool:
        """Resolve hostname and reject if any address is private/loopback/link-local/reserved."""
        try:
            for info in socket.getaddrinfo(hostname, 443, socket.AF_UNSPEC, socket.SOCK_STREAM):
                addr = ipaddress.ip_address(info[4][0])
                if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                    return True
        except socket.gaierror:
            return True  # fail-closed: unresolvable hosts are rejected
        return False

    def validate_url(self, url: str) -> dict:
        """Returns {"valid": True, "url": normalized} or {"valid": False, "error": ...}."""
        # Local file path
        if url.startswith("/"):
            return self._validate_local_path(url)

        # Remote URL
        try:
            parsed = urlparse(url)
        except Exception:
            return {"valid": False, "error": "invalid_url", "message": f"Cannot parse URL: {url}"}

        if parsed.scheme != "https":
            return {"valid": False, "error": "invalid_protocol", "message": "Only HTTPS URLs are allowed."}

        # Reject URLs with userinfo (e.g. https://user:pass@host/)
        if parsed.username or parsed.password:
            return {"valid": False, "error": "invalid_url", "message": "URLs with credentials are not allowed."}

        hostname = parsed.hostname or ""

        # Reject IP address literals (e.g. https://127.0.0.1/, https://[::1]/)
        if self._is_ip_literal(hostname):
            return {
                "valid": False,
                "error": "ip_literal_not_allowed",
                "message": "IP address literals are not allowed. Use a hostname.",
            }

        if not self._matches_domain(hostname):
            return {
                "valid": False,
                "error": "domain_not_allowed",
                "message": f"Domain {hostname} is not in the allowlist.",
            }

        # After domain allowlist passes, verify DNS does not resolve to private/internal IPs
        if self._resolves_to_private(hostname):
            return {
                "valid": False,
                "error": "private_ip_not_allowed",
                "message": f"Domain {hostname} resolves to a private/internal IP address.",
            }

        return {"valid": True, "url": url}

    def require_valid_url(self, url: str) -> str:
        """Returns validated URL or raises ValueError."""
        result = self.validate_url(url)
        if not result["valid"]:
            raise ValueError(result["message"])
        return result.get("url", url)

    def _validate_local_path(self, path: str) -> dict:
        """Validate local file path against media directory (path traversal protection)."""
        try:
            resolved = str(Path(path).resolve())
        except Exception:
            return {"valid": False, "error": "invalid_path", "message": "Cannot resolve path."}

        media_prefix = self._media_dir if self._media_dir.endswith(os.sep) else self._media_dir + os.sep
        if not (resolved == self._media_dir or resolved.startswith(media_prefix)):
            return {
                "valid": False,
                "error": "path_traversal",
                "message": "Path must be within the media directory.",
            }

        return {"valid": True, "url": resolved}
