from __future__ import annotations

GITHUB_API = "https://api.github.com"


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
