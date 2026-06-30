from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from jclee_bot.json_boundary import JsonObject

type StepStatus = Literal["ok", "failed"]
type RepoAction = Literal["ok", "failed", "skipped", "would_update", "updated", "would_apply", "applied", "listed"]


@dataclass(frozen=True, slots=True)
class MarkdownFinding:
    path: str
    line: int
    text: str

    def label(self) -> str:
        return f"{self.path}:{self.line} {self.text}"


@dataclass(frozen=True, slots=True)
class RepositoryAction:
    repo: str
    action: RepoAction
    detail: str = ""

    def to_dict(self) -> JsonObject:
        return {"repo": self.repo, "action": self.action, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class StandardizationStep:
    name: str
    status: StepStatus
    repositories: tuple[RepositoryAction, ...]

    def to_dict(self) -> JsonObject:
        return {
            "name": self.name,
            "status": self.status,
            "repositories": [action.to_dict() for action in self.repositories],
        }


def step_status(actions: list[RepositoryAction]) -> StepStatus:
    return "failed" if any(action.action == "failed" for action in actions) else "ok"
