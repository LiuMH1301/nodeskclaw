"""
URL allowlist factory for SSRF protection.

Usage:
    validator = create_url_validator(providers)
    validator.require_valid_url("https://api.openai.com/v1/images")

Adding a provider: No changes here. The new provider module declares its
allowed_domains, and server.py passes all providers to this factory.
"""

from __future__ import annotations

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

        if not self._matches_domain(parsed.hostname or ""):
            return {
                "valid": False,
                "error": "domain_not_allowed",
                "message": f"Domain {parsed.hostname} is not in the allowlist.",
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

        if not resolved.startswith(self._media_dir):
            return {
                "valid": False,
                "error": "path_traversal",
                "message": "Path must be within the media directory.",
            }

        return {"valid": True, "url": resolved}
