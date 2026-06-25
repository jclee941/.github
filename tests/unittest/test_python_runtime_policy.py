from __future__ import annotations

import sys
import tomllib
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_bounds_python_to_supported_automation_runtime() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    match pyproject:
        case {"project": {"requires-python": str(requires_python)}}:
            assert requires_python == ">=3.12,<3.14"
        case _:
            raise AssertionError("pyproject.toml must define project.requires-python")


def test_python_test_runner_matches_supported_floor() -> None:
    assert sys.version_info[:2] >= (3, 12)


def test_readme_python_runtime_matches_pyproject_policy() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "python-3.12--3.13" in readme
    assert "Python **3.12 or 3.13**" in readme
    assert "3.12+" not in readme


def test_make_install_accepts_supported_python_runtime_range() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "python3.12 -m venv" not in makefile
    assert "python3.13" in makefile
    assert "python3.12" in makefile


def test_fastapi_testclient_import_has_no_starlette_deprecation_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        from fastapi.testclient import TestClient

    assert TestClient.__name__ == "TestClient"
