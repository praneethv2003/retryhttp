"""Tests for RetryClient and AsyncRetryClient (httpx)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from retryhttp import AsyncRetryClient, RetryClient
from retryhttp.retry import RetryConfig, RetryExhausted


# ---------------------------------------------------------------------------
# Sync RetryClient
# ---------------------------------------------------------------------------


def test_successful_request(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=200, json={"ok": True})
    with RetryClient() as client:
        resp = client.get("https://example.com/api")
    assert resp.status_code == 200


def test_retries_on_503(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=200, json={"ok": True})

    cfg = RetryConfig(max_attempts=3, jitter=False, backoff_base=0.0001)
    with RetryClient(config=cfg) as client:
        resp = client.get("https://example.com/api")
    assert resp.status_code == 200


def test_raises_retry_exhausted(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)

    cfg = RetryConfig(max_attempts=3, jitter=False, backoff_base=0.0001)
    with pytest.raises(RetryExhausted) as exc_info:
        with RetryClient(config=cfg) as client:
            client.get("https://example.com/api")

    assert exc_info.value.attempts == 3
    assert exc_info.value.last_status == 503


def test_no_retry_on_404(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=404)

    cfg = RetryConfig(max_attempts=3)
    with RetryClient(config=cfg) as client:
        resp = client.get("https://example.com/api")
    assert resp.status_code == 404
    # Only one request should have been made.
    assert len(httpx_mock.get_requests()) == 1


def test_token_refresh_on_401(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=401)
    httpx_mock.add_response(status_code=200, json={"ok": True})

    refresh_calls: list[str] = []

    def refresher() -> str:
        refresh_calls.append("called")
        return "new-token-xyz"

    cfg = RetryConfig(max_attempts=3, jitter=False, backoff_base=0.0001)
    with RetryClient(config=cfg, token_refresher=refresher) as client:
        resp = client.get("https://example.com/api")

    assert resp.status_code == 200
    assert len(refresh_calls) == 1
    assert client.headers["Authorization"] == "Bearer new-token-xyz"


def test_raise_on_exhaust_false_returns_response(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)

    cfg = RetryConfig(max_attempts=3, jitter=False, backoff_base=0.0001, raise_on_exhaust=False)
    with RetryClient(config=cfg) as client:
        resp = client.get("https://example.com/api")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Async AsyncRetryClient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_successful_request(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=200, json={"ok": True})
    async with AsyncRetryClient() as client:
        resp = await client.get("https://example.com/api")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_async_retries_on_503(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=200, json={"ok": True})

    cfg = RetryConfig(max_attempts=3, jitter=False, backoff_base=0.0001)
    async with AsyncRetryClient(config=cfg) as client:
        resp = await client.get("https://example.com/api")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_async_token_refresh_on_401(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=401)
    httpx_mock.add_response(status_code=200, json={"ok": True})

    async def async_refresher() -> str:
        return "async-new-token"

    cfg = RetryConfig(max_attempts=3, jitter=False, backoff_base=0.0001)
    async with AsyncRetryClient(config=cfg, token_refresher=async_refresher) as client:
        resp = await client.get("https://example.com/api")

    assert resp.status_code == 200
    assert client.headers["Authorization"] == "Bearer async-new-token"


@pytest.mark.asyncio
async def test_async_raises_retry_exhausted(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)
    httpx_mock.add_response(status_code=503)

    cfg = RetryConfig(max_attempts=3, jitter=False, backoff_base=0.0001)
    with pytest.raises(RetryExhausted):
        async with AsyncRetryClient(config=cfg) as client:
            await client.get("https://example.com/api")
