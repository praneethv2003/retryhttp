"""Tests for the backoff delay calculation."""

import pytest

from retryhttp.backoff import backoff_delay


def test_no_jitter_grows_exponentially():
    delays = [backoff_delay(i, base=1.0, maximum=60.0, jitter=False) for i in range(5)]
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]


def test_maximum_caps_delay():
    delay = backoff_delay(100, base=1.0, maximum=10.0, jitter=False)
    assert delay == 10.0


def test_jitter_within_bounds():
    for attempt in range(10):
        d = backoff_delay(attempt, base=1.0, maximum=60.0, jitter=True)
        cap = min(60.0, 1.0 * (2**attempt))
        assert 0.0 <= d <= cap


def test_base_zero_raises():
    with pytest.raises(Exception):
        backoff_delay(0, base=0, maximum=10.0)
