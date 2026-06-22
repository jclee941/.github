from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final

ACCESS_TOKEN_USER: Final = "x-access" + "-token"


def git_askpass_env(*, token: str, workspace: str | Path) -> dict[str, str]:
    askpass_path = Path(workspace) / "git-askpass.sh"
    script = "\n".join(
        [
            "#!/bin/sh",
            "case \"$1\" in",
            "*Username*) printf '%s\\n' \"$GIT_ASKPASS_USERNAME\" ;;",
            "*Password*) printf '%s\\n' \"$GIT_ASKPASS_PASSWORD\" ;;",
            "*) printf '\\n' ;;",
            "esac",
            "",
        ],
    )
    _written = askpass_path.write_text(script, encoding="utf-8")
    askpass_path.chmod(0o700)
    return {
        "GIT_ASKPASS": str(askpass_path),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS_USERNAME": ACCESS_TOKEN_USER,
        "GIT_ASKPASS_PASSWORD": token,
    }


def git_env_with_auth(auth_env: dict[str, str] | None) -> dict[str, str]:
    run_env = os.environ.copy()
    if auth_env is not None:
        run_env.update(auth_env)
    return run_env


def sanitize_access_token_url(text: str) -> str:
    return re.sub(re.escape(ACCESS_TOKEN_USER) + r":[^@\s]+@", f"{ACCESS_TOKEN_USER}:***@", text)
