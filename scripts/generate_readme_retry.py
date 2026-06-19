from __future__ import annotations

import urllib.error

TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504, 520, 522, 524}


class TransientLLMError(RuntimeError):
    pass


def is_transient(error: Exception) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code in TRANSIENT_HTTP_CODES
    if isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return True
    return isinstance(error, OSError)
