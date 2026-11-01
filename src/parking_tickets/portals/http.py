import time
from importlib.metadata import version
from urllib.parse import urlsplit

import httpx

USER_AGENT = (
    f"parking-tickets/{version('parking-tickets')}"
    " (+https://github.com/ivanvia7/parking-tickets)"
)
MIN_GAP_SECONDS = 1.0

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


def get_json(url: str, params: dict[str, str], headers: dict[str, str]) -> object:
    wait_turn(urlsplit(url).netloc)
    response = CLIENT.get(url, params=params, headers=headers)
    if response.is_error:
        raise RuntimeError(
            f"{response.status_code} from {response.url}: {response.text[:300]}"
        )
    return response.json()
