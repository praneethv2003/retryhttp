"""httpx adapters: RetryClient (sync) and AsyncRetryClient."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from retryhttp.backoff import backoff_delay
from retryhttp.retry import RetryConfig, RetryExhausted

logger = logging.getLogger(__name__)

# Types for the token-refresh callable.
# Sync: () -> str  |  Async: async () -> str
TokenRefresher = Callable[[], str]
AsyncTokenRefresher = Callable[[], Any]  # must be a coroutine function


class RetryClient(httpx.Client):
    """An httpx.Client that retries failed requests with exponential backoff.

    Args:
        config: Retry policy. Defaults to RetryConfig() (3 attempts, sane backoff).
        token_refresher: Optional callable ``() -> str`` that returns a fresh
            bearer token. Called automatically on 401 responses. The new token
            is injected into ``self.headers["Authorization"]`` before the retry.
        **kwargs: Forwarded verbatim to httpx.Client.

    Example::

        def refresh() -> str:
            return fetch_new_token()

        with RetryClient(token_refresher=refresh) as client:
            resp = client.get("https://api.example.com/data")
    """

    def __init__(
        self,
        *,
        config: RetryConfig | None = None,
        token_refresher: TokenRefresher | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.retry_config = config or RetryConfig()
        self._token_refresher = token_refresher

    def _maybe_refresh_token(self) -> None:
        if self._token_refresher is not None:
            new_token = self._token_refresher()
            self.headers["Authorization"] = f"Bearer {new_token}"
            logger.debug("retryhttp: token refreshed")

    def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:  # type: ignore[override]
        cfg = self.retry_config
        last_exc: Exception | None = None
        last_response: httpx.Response | None = None

        for attempt in range(cfg.max_attempts):
            try:
                response = super().send(request, **kwargs)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                if not cfg.retry_on_network_error or attempt == cfg.max_attempts - 1:
                    raise
                last_exc = exc
                delay = backoff_delay(attempt, base=cfg.backoff_base, maximum=cfg.backoff_max, jitter=cfg.jitter)
                logger.warning(
                    "retryhttp: network error on attempt %d/%d (%s), retrying in %.2fs",
                    attempt + 1,
                    cfg.max_attempts,
                    exc,
                    delay,
                )
                time.sleep(delay)
                continue

            last_response = response
            last_exc = None

            # Token refresh on 401.
            if cfg.token_refresh_status and response.status_code == cfg.token_refresh_status:
                if attempt < cfg.max_attempts - 1:
                    logger.info("retryhttp: 401 received, refreshing token (attempt %d)", attempt + 1)
                    self._maybe_refresh_token()
                    # Re-build the request so the new Authorization header is sent.
                    request = self.build_request(
                        method=request.method,
                        url=request.url,
                        content=request.content,
                        headers=dict(request.headers),
                    )
                    continue

            if not cfg.should_retry_status(response.status_code):
                return response

            if attempt == cfg.max_attempts - 1:
                if cfg.raise_on_exhaust:
                    raise RetryExhausted(
                        f"All {cfg.max_attempts} attempts failed",
                        attempts=cfg.max_attempts,
                        last_status=response.status_code,
                    )
                return response

            delay = backoff_delay(attempt, base=cfg.backoff_base, maximum=cfg.backoff_max, jitter=cfg.jitter)
            logger.warning(
                "retryhttp: HTTP %d on attempt %d/%d, retrying in %.2fs",
                response.status_code,
                attempt + 1,
                cfg.max_attempts,
                delay,
            )
            time.sleep(delay)

        # Should only be reached via network-error path exhaustion.
        if cfg.raise_on_exhaust:
            raise RetryExhausted(
                f"All {cfg.max_attempts} attempts failed",
                attempts=cfg.max_attempts,
                last_status=last_response.status_code if last_response else None,
            )
        assert last_response is not None
        return last_response


class AsyncRetryClient(httpx.AsyncClient):
    """An async httpx.AsyncClient that retries with exponential backoff.

    Args:
        config: Retry policy.
        token_refresher: Optional *async* callable ``async () -> str``.
        **kwargs: Forwarded to httpx.AsyncClient.

    Example::

        async def refresh() -> str:
            return await fetch_new_token_async()

        async with AsyncRetryClient(token_refresher=refresh) as client:
            resp = await client.get("https://api.example.com/data")
    """

    def __init__(
        self,
        *,
        config: RetryConfig | None = None,
        token_refresher: AsyncTokenRefresher | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.retry_config = config or RetryConfig()
        self._token_refresher = token_refresher

    async def _maybe_refresh_token(self) -> None:
        if self._token_refresher is not None:
            if asyncio.iscoroutinefunction(self._token_refresher):
                new_token = await self._token_refresher()
            else:
                new_token = self._token_refresher()
            self.headers["Authorization"] = f"Bearer {new_token}"
            logger.debug("retryhttp: token refreshed (async)")

    async def send(self, request: httpx.Request, **kwargs: Any) -> httpx.Response:  # type: ignore[override]
        cfg = self.retry_config
        last_response: httpx.Response | None = None

        for attempt in range(cfg.max_attempts):
            try:
                response = await super().send(request, **kwargs)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                if not cfg.retry_on_network_error or attempt == cfg.max_attempts - 1:
                    raise
                delay = backoff_delay(attempt, base=cfg.backoff_base, maximum=cfg.backoff_max, jitter=cfg.jitter)
                logger.warning(
                    "retryhttp: network error on attempt %d/%d (%s), retrying in %.2fs",
                    attempt + 1,
                    cfg.max_attempts,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            last_response = response

            if cfg.token_refresh_status and response.status_code == cfg.token_refresh_status:
                if attempt < cfg.max_attempts - 1:
                    logger.info("retryhttp: 401 received, refreshing token (attempt %d)", attempt + 1)
                    await self._maybe_refresh_token()
                    request = self.build_request(
                        method=request.method,
                        url=request.url,
                        content=request.content,
                        headers=dict(request.headers),
                    )
                    continue

            if not cfg.should_retry_status(response.status_code):
                return response

            if attempt == cfg.max_attempts - 1:
                if cfg.raise_on_exhaust:
                    raise RetryExhausted(
                        f"All {cfg.max_attempts} attempts failed",
                        attempts=cfg.max_attempts,
                        last_status=response.status_code,
                    )
                return response

            delay = backoff_delay(attempt, base=cfg.backoff_base, maximum=cfg.backoff_max, jitter=cfg.jitter)
            logger.warning(
                "retryhttp: HTTP %d on attempt %d/%d, retrying in %.2fs",
                response.status_code,
                attempt + 1,
                cfg.max_attempts,
                delay,
            )
            await asyncio.sleep(delay)

        if cfg.raise_on_exhaust:
            raise RetryExhausted(
                f"All {cfg.max_attempts} attempts failed",
                attempts=cfg.max_attempts,
                last_status=last_response.status_code if last_response else None,
            )
        assert last_response is not None
        return last_response
