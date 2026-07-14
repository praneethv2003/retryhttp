"""requests adapter: RetrySession."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import requests
from requests import PreparedRequest, Response
from requests.adapters import HTTPAdapter

from retryhttp.backoff import backoff_delay
from retryhttp.retry import RetryConfig, RetryExhausted

logger = logging.getLogger(__name__)

TokenRefresher = Callable[[], str]


class _RetryAdapter(HTTPAdapter):
    """Internal HTTPAdapter that carries a RetryConfig.

    The actual retry loop lives in RetrySession.send so that the token-refresh
    hook has access to the session-level headers.
    """

    def __init__(self, config: RetryConfig, **kwargs: Any) -> None:
        self.retry_config = config
        super().__init__(**kwargs)


class RetrySession(requests.Session):
    """A requests.Session that retries failed requests with exponential backoff.

    Args:
        config: Retry policy. Defaults to RetryConfig() (3 attempts, sane backoff).
        token_refresher: Optional callable ``() -> str`` that returns a fresh
            bearer token. Triggered on 401 responses.
        **kwargs: Not used; present for forward-compatibility.

    Example::

        def refresh() -> str:
            return fetch_new_token()

        with RetrySession(token_refresher=refresh) as session:
            resp = session.get("https://api.example.com/data")
    """

    def __init__(
        self,
        *,
        config: RetryConfig | None = None,
        token_refresher: TokenRefresher | None = None,
    ) -> None:
        super().__init__()
        self.retry_config = config or RetryConfig()
        self._token_refresher = token_refresher

        adapter = _RetryAdapter(self.retry_config)
        self.mount("https://", adapter)
        self.mount("http://", adapter)

    def _maybe_refresh_token(self) -> None:
        if self._token_refresher is not None:
            new_token = self._token_refresher()
            self.headers["Authorization"] = f"Bearer {new_token}"
            logger.debug("retryhttp: token refreshed")

    def send(self, request: PreparedRequest, **kwargs: Any) -> Response:  # type: ignore[override]
        cfg = self.retry_config
        last_response: Response | None = None

        for attempt in range(cfg.max_attempts):
            try:
                response = super().send(request, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
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
                time.sleep(delay)
                continue

            last_response = response

            # Token refresh on 401.
            if cfg.token_refresh_status and response.status_code == cfg.token_refresh_status:
                if attempt < cfg.max_attempts - 1:
                    logger.info("retryhttp: 401 received, refreshing token (attempt %d)", attempt + 1)
                    self._maybe_refresh_token()
                    # Re-prepare the request so the updated session headers are baked in.
                    req = response.request
                    assert req.url is not None
                    prepped = self.prepare_request(
                        requests.Request(
                            method=req.method or "GET",
                            url=req.url,
                            headers=dict(self.headers),
                            data=req.body,
                        )
                    )
                    request = prepped
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

        if cfg.raise_on_exhaust:
            raise RetryExhausted(
                f"All {cfg.max_attempts} attempts failed",
                attempts=cfg.max_attempts,
                last_status=last_response.status_code if last_response else None,
            )
        assert last_response is not None
        return last_response
