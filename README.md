# retryhttp

Zero-config HTTP retries with exponential backoff, jitter, and OAuth2 token refresh — for both **httpx** and **requests**.

```python
from retryhttp import RetryClient

with RetryClient(token_refresher=lambda: fetch_token()) as client:
    resp = client.get("https://api.example.com/data")
```

## Why

Every team rewrites retry logic from scratch. `retryhttp` gives you:

- **Exponential backoff with full jitter** (AWS-recommended strategy)
- **Token refresh hooks** — pass a callable, 401s are handled automatically
- **Per-status-code retry policies** — retry 503 but not 404
- **Network error retries** — connection errors and timeouts included
- **Async support** via `AsyncRetryClient`
- **Drop-in replacements** — subclasses `httpx.Client` and `requests.Session`, so existing code works unchanged

## Install

```bash
# httpx support
pip install "retryhttp[httpx]"

# requests support
pip install "retryhttp[requests]"

# both
pip install "retryhttp[all]"
```

## Usage

### httpx (sync)

```python
from retryhttp import RetryClient, RetryConfig

config = RetryConfig(
    max_attempts=5,
    backoff_base=0.5,
    backoff_max=30.0,
    retry_statuses=frozenset({429, 500, 502, 503, 504}),
)

def get_token() -> str:
    # call your auth server
    return "new-bearer-token"

with RetryClient(config=config, token_refresher=get_token) as client:
    resp = client.get("https://api.example.com/resource")
    print(resp.json())
```

### httpx (async)

```python
import asyncio
from retryhttp import AsyncRetryClient

async def get_token() -> str:
    return "new-bearer-token"

async def main():
    async with AsyncRetryClient(token_refresher=get_token) as client:
        resp = await client.get("https://api.example.com/resource")
        print(resp.json())

asyncio.run(main())
```

### requests

```python
from retryhttp import RetrySession

with RetrySession(token_refresher=lambda: "new-token") as session:
    resp = session.get("https://api.example.com/resource")
```

## Configuration

`RetryConfig` controls all retry behaviour:

| Parameter | Default | Description |
|---|---|---|
| `max_attempts` | `3` | Total attempts (1 = no retries) |
| `retry_statuses` | `{429,500,502,503,504}` | Status codes that trigger a retry |
| `backoff_base` | `1.0` | Base backoff in seconds |
| `backoff_max` | `60.0` | Maximum backoff ceiling |
| `jitter` | `True` | Full jitter on each delay |
| `retry_on_network_error` | `True` | Retry on connection/timeout errors |
| `token_refresh_status` | `401` | Status that triggers token refresh |
| `raise_on_exhaust` | `True` | Raise `RetryExhausted` when all attempts fail; `False` returns the last response |

## How backoff works

Uses AWS's **Full Jitter** strategy:

```
cap = min(backoff_max, backoff_base × 2^attempt)
sleep = random(0, cap)
```

This avoids thundering-herd problems when many clients retry simultaneously.

## Exceptions

```python
from retryhttp import RetryExhausted

try:
    client.get("https://api.example.com")
except RetryExhausted as e:
    print(f"Failed after {e.attempts} attempts, last status: {e.last_status}")
```

## Development

```bash
git clone https://github.com/praneethvedantham/retryhttp
cd retryhttp
pip install -e ".[dev]"
pytest
```

## License

MIT
