from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final

import requests

MAX_GITHUB_REQUEST_ATTEMPTS: Final = 3
GITHUB_RETRY_DELAY_SECONDS: Final = 2.0
RETRYABLE_STATUS_CODES: Final = frozenset({429, 500, 502, 503, 504})


def github_request(send: Callable[[], requests.Response]) -> requests.Response:
    for attempt in range(1, MAX_GITHUB_REQUEST_ATTEMPTS + 1):
        try:
            response = send()
            response.raise_for_status()
        except (requests.ConnectionError, requests.Timeout):
            if attempt == MAX_GITHUB_REQUEST_ATTEMPTS:
                raise
            sleep_before_retry()
            continue
        except requests.HTTPError as exc:
            if attempt == MAX_GITHUB_REQUEST_ATTEMPTS or not is_retryable_http_error(exc):
                raise
            sleep_before_retry()
            continue
        else:
            return response
    raise RuntimeError("unreachable GitHub retry state")


def sleep_before_retry() -> None:
    time.sleep(GITHUB_RETRY_DELAY_SECONDS)


def is_retryable_http_error(exc: requests.HTTPError) -> bool:
    response = exc.response
    return response is not None and response.status_code in RETRYABLE_STATUS_CODES


def is_retryable_request_exception(exc: requests.RequestException) -> bool:
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exc, requests.HTTPError):
        return is_retryable_http_error(exc)
    return False
