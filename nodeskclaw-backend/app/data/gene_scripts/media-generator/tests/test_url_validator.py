"""Unit tests for URL validator factory."""

import pytest
from lib.url_validator import create_url_validator

MOCK_PROVIDERS = [
    {"allowed_domains": ["api.openai.com", "oaidalleapiprodscus.blob.core.windows.net"]},
    {"allowed_domains": ["api.dev.runwayml.com"]},
]


@pytest.fixture
def validator(tmp_path):
    media_dir = str(tmp_path / "media")
    (tmp_path / "media").mkdir()
    return create_url_validator(MOCK_PROVIDERS, media_dir)


def test_allows_openai_domain(validator):
    result = validator.validate_url("https://api.openai.com/v1/images")
    assert result["valid"] is True


def test_allows_runway_domain(validator):
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


def test_rejects_internal_ip(validator):
    result = validator.validate_url("https://169.254.169.254/metadata")
    assert result["valid"] is False


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


def test_accepts_subdomain_of_allowed_domain(validator):
    result = validator.validate_url("https://cdn.api.openai.com/files/123")
    assert result["valid"] is True


def test_path_traversal_error_does_not_leak_media_dir(validator, tmp_path):
    traversal = str(tmp_path / "media" / ".." / ".." / "etc" / "passwd")
    result = validator.validate_url(traversal)
    assert "media directory" in result["message"]
    assert str(tmp_path) not in result["message"]


def test_require_valid_url_raises_on_invalid(validator):
    with pytest.raises(ValueError):
        validator.require_valid_url("http://evil.com/bad")
