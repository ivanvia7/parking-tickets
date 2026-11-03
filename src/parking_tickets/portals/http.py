import time
from importlib.metadata import version
from typing import Any
from urllib.parse import urlsplit

import httpx

USER_AGENT = (
    f"parking-tickets/{version('parking-tickets')}"
    " (+https://github.com/ivanvia7/parking-tickets)"
)
MIN_GAP_SECONDS = 1.0
RETRY_STATUSES = {429, 500, 502, 503, 504}
# The monthly release reads every year of every city; a few slow answers in
# about 3 million calls are normal, so a call gets 5 tries over about 50 seconds.
ATTEMPTS = 5
RETRY_SECONDS = 5.0
MAX_RETRY_SECONDS = 60.0

# IPv4 only: an IPv6 fallback on some networks hides the real connect error.
CLIENT = httpx.Client(
    headers={"User-Agent": USER_AGENT},
    # NYC answered some 2014 days only after more than 60 seconds.
    timeout=120,
    follow_redirects=True,
    transport=httpx.HTTPTransport(local_address="0.0.0.0"),
)
_last_call: dict[str, float] = {}


def wait_turn(host: str) -> None:
    gap = time.monotonic() - _last_call.get(host, 0.0)
    if gap < MIN_GAP_SECONDS:
        time.sleep(MIN_GAP_SECONDS - gap)
    _last_call[host] = time.monotonic()


def is_busy(response: httpx.Response) -> bool:
    """Carto answers 400 query_wait_timeout when its query queue is full."""
    if response.status_code in RETRY_STATUSES:
        return True
    return response.status_code == 400 and "query_wait_timeout" in response.text


def retry_delay(response: httpx.Response, attempt: int) -> float:
    after = response.headers.get("Retry-After", "")
    wait = float(after) if after.isdigit() else RETRY_SECONDS * attempt
    return min(wait, MAX_RETRY_SECONDS)


def get_json(url: str, params: dict[str, str], headers: dict[str, str]) -> Any:
    attempt = 1
    while True:
        wait_turn(urlsplit(url).netloc)
        try:
            response = CLIENT.get(url, params=params, headers=headers)
        except httpx.TransportError as error:
            if attempt == ATTEMPTS:
                raise RuntimeError(
                    f"{error!r} from {url} after {ATTEMPTS} tries"
                ) from error
            time.sleep(RETRY_SECONDS * attempt)
        else:
            if not is_busy(response) or attempt == ATTEMPTS:
                break
            time.sleep(retry_delay(response, attempt))
        attempt += 1
    if response.is_error:
        raise RuntimeError(
            f"{response.status_code} from {response.url}: {response.text[:300]}"
        )
    try:
        return response.json()
    except ValueError as error:
        raise RuntimeError(
            f"not JSON from {response.url}: {response.text[:300]}"
        ) from error
