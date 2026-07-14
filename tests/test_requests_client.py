"""Tests for RetrySession (requests)."""

from __future__ import annotations

import pytest
import responses as resp_mock
from responses import RequestsMock

from retryhttp import RetrySession
from retryhttp.retry import RetryConfig, RetryExhausted


@resp_mock.activate
def test_successful_request():
    resp_mock.add(resp_mock.GET, "https://example.com/api", status=200, json={"ok": True})
    with RetrySession() as session:
        resp = session.get("https://example.com/api")
    assert resp.status_code == 200


@resp_mock.activate
def test_retries_on_503():
    resp_mock.add(resp_mock.GET, "https://example.com/api", status=503)
    resp_mock.add(resp_mock.GET, "https://example.com/api", status=503)
    resp_mock.add(resp_mock.GET, "https://example.com/api", status=200, json={"ok": True})

    cfg = RetryConfig(max_attempts=3, jitter=False, backoff_base=0.0001)
    with RetrySession(config=cfg) as session:
        resp = session.get("https://example.com/api")
    assert resp.status_code == 200


@resp_mock.activate
def test_raises_retry_exhausted():
    for _ in range(3):
        resp_mock.add(resp_mock.GET, "https://example.com/api", status=503)

    cfg = RetryConfig(max_attempts=3, jitter=False, backoff_base=0.0001)
    with pytest.raises(RetryExhausted) as exc_info:
        with RetrySession(config=cfg) as session:
            session.get("https://example.com/api")

    assert exc_info.value.attempts == 3
    assert exc_info.value.last_status == 503


@resp_mock.activate
def test_no_retry_on_404():
    resp_mock.add(resp_mock.GET, "https://example.com/api", status=404)

    with RetrySession() as session:
        resp = session.get("https://example.com/api")
    assert resp.status_code == 404
    assert len(resp_mock.calls) == 1


@resp_mock.activate
def test_token_refresh_on_401():
    resp_mock.add(resp_mock.GET, "https://example.com/api", status=401)
    resp_mock.add(resp_mock.GET, "https://example.com/api", status=200, json={"ok": True})

    calls: list[str] = []

    def refresher() -> str:
        calls.append("called")
        return "fresh-token"

    cfg = RetryConfig(max_attempts=3, jitter=False, backoff_base=0.0001)
    with RetrySession(config=cfg, token_refresher=refresher) as session:
        resp = session.get("https://example.com/api")

    assert resp.status_code == 200
    assert len(calls) == 1


@resp_mock.activate
def test_raise_on_exhaust_false_returns_response():
    for _ in range(3):
        resp_mock.add(resp_mock.GET, "https://example.com/api", status=503)

    cfg = RetryConfig(max_attempts=3, jitter=False, backoff_base=0.0001, raise_on_exhaust=False)
    with RetrySession(config=cfg) as session:
        resp = session.get("https://example.com/api")
    assert resp.status_code == 503
