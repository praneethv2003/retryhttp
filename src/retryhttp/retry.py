"""Core retry configuration and exception types."""

from __future__ import annotations

from dataclasses import dataclass, field


# HTTP status codes that are safe to retry by default.
DEFAULT_RETRY_STATUSES: frozenset[int] = frozenset(
    {
        429,  # Too Many Requests
        500,  # Internal Server Error
        502,  # Bad Gateway
        503,  # Service Unavailable
        504,  # Gateway Timeout
    }
)


class RetryExhausted(Exception):
    """Raised when all retry attempts have been spent.

    Attributes:
        attempts: Number of attempts made before giving up.
        last_status: HTTP status code of the final response, or None if the
            last attempt raised a network-level exception.
    """

    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        last_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_status = last_status


@dataclass
class RetryConfig:
    """Declarative retry policy passed to RetryClient / RetrySession.

    Args:
        max_attempts: Total number of attempts (1 = no retries).
        retry_statuses: Set of HTTP status codes that trigger a retry.
        backoff_base: Base for exponential backoff in seconds.
        backoff_max: Maximum backoff ceiling in seconds.
        jitter: When True, adds random jitter to each backoff delay.
        retry_on_network_error: Retry on connection errors, timeouts, etc.
        token_refresh_status: Status code that triggers a token refresh
            (default 401). Set to None to disable.
        raise_on_exhaust: Raise RetryExhausted when all attempts fail.
            When False, the final bad response is returned instead.

    Example::

        config = RetryConfig(max_attempts=5, backoff_base=0.5)
        client = RetryClient(config=config, token_refresher=my_refresh_fn)
    """

    max_attempts: int = 3
    retry_statuses: frozenset[int] = field(default_factory=lambda: DEFAULT_RETRY_STATUSES)
    backoff_base: float = 1.0
    backoff_max: float = 60.0
    jitter: bool = True
    retry_on_network_error: bool = True
    token_refresh_status: int | None = 401
    raise_on_exhaust: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.backoff_base <= 0:
            raise ValueError("backoff_base must be positive")
        if self.backoff_max < self.backoff_base:
            raise ValueError("backoff_max must be >= backoff_base")

    def should_retry_status(self, status: int) -> bool:
        """Return True if *status* is in the retry set."""
        return status in self.retry_statuses
