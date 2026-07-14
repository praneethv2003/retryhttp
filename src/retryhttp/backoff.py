"""Backoff delay calculation."""

from __future__ import annotations

import random


def backoff_delay(
    attempt: int,
    *,
    base: float = 1.0,
    maximum: float = 60.0,
    jitter: bool = True,
) -> float:
    """Compute an exponential backoff delay with optional full jitter.

    Uses the "Full Jitter" strategy from AWS architecture blog:
    https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

    Args:
        attempt: Zero-indexed attempt number (0 = first retry → shortest delay).
        base: Backoff base in seconds.
        maximum: Hard ceiling on the computed delay.
        jitter: When True, randomise within [0, computed_cap].

    Returns:
        Seconds to sleep before the next attempt.

    Example::

        for i in range(3):
            time.sleep(backoff_delay(i, base=0.5, maximum=30))
    """
    if base <= 0:
        raise ValueError("base must be positive")
    cap = min(maximum, base * (2**attempt))
    if jitter:
        return random.uniform(0, cap)
    return cap
