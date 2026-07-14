"""Tests for RetryConfig validation and behaviour."""

import pytest

from retryhttp.retry import DEFAULT_RETRY_STATUSES, RetryConfig


def test_defaults():
    cfg = RetryConfig()
    assert cfg.max_attempts == 3
    assert cfg.jitter is True
    assert cfg.retry_statuses == DEFAULT_RETRY_STATUSES


def test_should_retry_status():
    cfg = RetryConfig()
    assert cfg.should_retry_status(503) is True
    assert cfg.should_retry_status(200) is False
    assert cfg.should_retry_status(404) is False


def test_invalid_max_attempts():
    with pytest.raises(ValueError, match="max_attempts"):
        RetryConfig(max_attempts=0)


def test_invalid_backoff_base():
    with pytest.raises(ValueError, match="backoff_base"):
        RetryConfig(backoff_base=0)


def test_backoff_max_lt_base():
    with pytest.raises(ValueError, match="backoff_max"):
        RetryConfig(backoff_base=10.0, backoff_max=5.0)


def test_custom_retry_statuses():
    cfg = RetryConfig(retry_statuses=frozenset({503, 429}))
    assert cfg.should_retry_status(503)
    assert not cfg.should_retry_status(500)
