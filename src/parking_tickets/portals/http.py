import time
from importlib.metadata import version
from urllib.parse import urlsplit

import httpx

USER_AGENT = (
    f"parking-tickets/{version('parking-tickets')}"
    " (+https://github.com/ivanvia7/parking-tickets)"
)
MIN_GAP_SECONDS = 1.0
RETRY_STATUSES = {429, 500, 502, 503, 504}
ATTEMPTS = 3
RETRY_SECONDS = 5.0

# IPv4 only: an IPv6 fallback on some networks hides the real connect error.
CLIENT = httpx.Client(
    headers={"User-Agent": USER_AGENT},
    timeout=60,
    follow_redirects=True,
    transport=httpx.HTTPTransport(local_address="0.0.0.0", retries=3),
)
_last_call: dict[str, float] = {}


def wait_turn(host: str) -> None:
    gap = time.monotonic() - _last_call.get(host, 0.0)
    if gap < MIN_GAP_SECONDS:
        time.sleep(MIN_GAP_SECONDS - gap)
    _last_call[host] = time.monotonic()


def retry_delay(response: httpx.Response, attempt: int) -> float:
    after = response.headers.get("Retry-After", "")
    return float(after) if after.isdigit() else RETRY_SECONDS * attempt


def get_json(url: str, params: dict[str, str], headers: dict[str, str]) -> object:
    for attempt in range(1, ATTEMPTS + 1):
        wait_turn(urlsplit(url).netloc)
        response = CLIENT.get(url, params=params, headers=headers)
        if response.status_code not in RETRY_STATUSES or attempt == ATTEMPTS:
            break
        time.sleep(retry_delay(response, attempt))
    if response.is_error:
        raise RuntimeError(
            f"{response.status_code} from {response.url}: {response.text[:300]}"
        )
    return response.json()
