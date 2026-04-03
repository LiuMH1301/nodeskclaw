"""Unit tests for URL validator factory."""

import socket
from unittest.mock import patch

import pytest
from lib.url_validator import create_url_validator, UrlValidator

MOCK_PROVIDERS = [
    {"allowed_domains": ["api.openai.com", "oaidalleapiprodscus.blob.core.windows.net"]},
    {"allowed_domains": ["api.dev.runwayml.com"]},
]


@pytest.fixture
def validator(tmp_path):
    media_dir = str(tmp_path / "media")
    (tmp_path / "media").mkdir()
    return create_url_validator(MOCK_PROVIDERS, media_dir)


@patch.object(UrlValidator, "_resolves_to_private", return_value=False)
def test_allows_openai_domain(_mock, validator):
    result = validator.validate_url("https://api.openai.com/v1/images")
    assert result["valid"] is True


@patch.object(UrlValidator, "_resolves_to_private", return_value=False)
def test_allows_runway_domain(_mock, validator):
    result = validator.validate_url("https://api.dev.runwayml.com/v1/tasks")
    assert result["valid"] is True


def test_rejects_http(validator):
    result = validator.validate_url("http://api.openai.com/v1/images")
    assert result["valid"] is False
    assert result["error"] == "invalid_protocol"


def test_rejects_unknown_domain(validator):
    result = validator.validate_url("https://evil.com/steal")
    assert result["valid"] is False
    assert result["error"] == "domain_not_allowed"


def test_rejects_ip_literal(validator):
    result = validator.validate_url("https://169.254.169.254/metadata")
    assert result["valid"] is False
    assert result["error"] == "ip_literal_not_allowed"


def test_rejects_ipv6_literal(validator):
    result = validator.validate_url("https://[::1]/metadata")
    assert result["valid"] is False
    assert result["error"] == "ip_literal_not_allowed"


def test_rejects_loopback_ip_literal(validator):
    result = validator.validate_url("https://127.0.0.1/secret")
    assert result["valid"] is False
    assert result["error"] == "ip_literal_not_allowed"


def test_allows_local_media_path(validator, tmp_path):
    media_file = tmp_path / "media" / "test.png"
    media_file.write_bytes(b"fake")
    result = validator.validate_url(str(media_file))
    assert result["valid"] is True


def test_rejects_path_traversal(validator, tmp_path):
    traversal = str(tmp_path / "media" / ".." / ".." / "etc" / "passwd")
    result = validator.validate_url(traversal)
    assert result["valid"] is False
    assert result["error"] == "path_traversal"


def test_rejects_url_encoded_traversal(validator, tmp_path):
    """Path.resolve() handles this -- %2e%2e in raw string won't match media dir."""
    result = validator.validate_url("/root/.deskclaw/media/%2e%2e/%2e%2e/etc/passwd")
    assert result["valid"] is False


def test_rejects_urls_with_userinfo(validator):
    result = validator.validate_url("https://user:pass@api.openai.com/v1")
    assert result["valid"] is False
    assert result["error"] == "invalid_url"


@patch.object(UrlValidator, "_resolves_to_private", return_value=False)
def test_accepts_subdomain_of_allowed_domain(_mock, validator):
    result = validator.validate_url("https://cdn.api.openai.com/files/123")
    assert result["valid"] is True


def test_path_traversal_error_does_not_leak_media_dir(validator, tmp_path):
    traversal = str(tmp_path / "media" / ".." / ".." / "etc" / "passwd")
    result = validator.validate_url(traversal)
    assert "media directory" in result["message"]
    assert str(tmp_path) not in result["message"]


@patch.object(UrlValidator, "_resolves_to_private", return_value=True)
def test_rejects_domain_resolving_to_private_ip(_mock, validator):
    result = validator.validate_url("https://api.openai.com/v1/images")
    assert result["valid"] is False
    assert result["error"] == "private_ip_not_allowed"


def test_require_valid_url_raises_on_invalid(validator):
    with pytest.raises(ValueError):
        validator.require_valid_url("http://evil.com/bad")


@patch("lib.url_validator.socket.getaddrinfo")
def test_dns_resolution_rejects_private_ip(mock_getaddrinfo, validator):
    """Mock DNS to return a private IP -- should be rejected."""
    mock_getaddrinfo.return_value = [
        (2, 1, 6, "", ("10.0.0.1", 443)),
    ]
    result = validator.validate_url("https://api.openai.com/v1/images")
    assert result["valid"] is False
    assert result["error"] == "private_ip_not_allowed"


@patch("lib.url_validator.socket.getaddrinfo")
def test_dns_resolution_rejects_loopback(mock_getaddrinfo, validator):
    """Mock DNS to return loopback -- should be rejected."""
    mock_getaddrinfo.return_value = [
        (2, 1, 6, "", ("127.0.0.1", 443)),
    ]
    result = validator.validate_url("https://api.openai.com/v1/images")
    assert result["valid"] is False
    assert result["error"] == "private_ip_not_allowed"


@patch("lib.url_validator.socket.getaddrinfo")
def test_dns_resolution_allows_public_ip(mock_getaddrinfo, validator):
    """Mock DNS to return public IP -- should be allowed."""
    mock_getaddrinfo.return_value = [
        (2, 1, 6, "", ("104.18.32.47", 443)),
    ]
    result = validator.validate_url("https://api.openai.com/v1/images")
    assert result["valid"] is True


@patch("lib.url_validator.socket.getaddrinfo", side_effect=socket.gaierror("DNS failure"))
def test_dns_resolution_failure_rejects(mock_getaddrinfo, validator):
    """Unresolvable hosts should be rejected (fail-closed)."""
    result = validator.validate_url("https://api.openai.com/v1/images")
    assert result["valid"] is False
    assert result["error"] == "private_ip_not_allowed"


def test_is_ip_literal_detects_ipv4():
    assert UrlValidator._is_ip_literal("192.168.1.1") is True


def test_is_ip_literal_detects_ipv6():
    assert UrlValidator._is_ip_literal("[::1]") is True


def test_is_ip_literal_rejects_hostname():
    assert UrlValidator._is_ip_literal("api.openai.com") is False
