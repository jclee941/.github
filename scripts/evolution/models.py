"""Pure data models for the evolution package.

No SQLite, no network, no LLM. Only dataclasses, enums and callable type
aliases so the core services can be unit-tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Generic, Mapping, Sequence, TypeVar

T = TypeVar("T")


class FindingStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    IGNORED = "ignored"


class FindingEventType(StrEnum):
    SEEN = "seen"
    CLOSED = "closed"
    REOPENED = "reopened"
    REGRESSED = "regressed"
    IGNORED = "ignored"


class SuggestionOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class RefinementStopReason(StrEnum):
    THRESHOLD_REACHED = "threshold_reached"
    MAX_ITERATIONS = "max_iterations"
    OSCILLATION_DETECTED = "oscillation_detected"
    NO_MONOTONIC_IMPROVEMENT = "no_monotonic_improvement"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    GENERATOR_STALLED = "generator_stalled"


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    category: str
    severity: str
    title: str
    content: str
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0


@dataclass(frozen=True, slots=True)
class FindingIdentity:
    fingerprint: str
    fingerprint_full: str
    marker_input: str
    normalized_content: str


@dataclass(frozen=True, slots=True)
class PullRequestContext:
    repo: str
    pr_url: str | None = None
    pr_number: int | None = None
    commit_sha: str | None = None


@dataclass(frozen=True, slots=True)
class RegressionMatch:
    finding: ReviewFinding
    fingerprint: str
    previous_status: FindingStatus
    first_pr_url: str | None
    first_pr_number: int | None
    closed_at: str | None
    is_regression: bool
    reason: str


@dataclass(frozen=True, slots=True)
class Suggestion:
    suggestion_id: str
    category: str
    label: str
    text: str
    score: float
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdjustedSuggestion:
    suggestion: Suggestion
    weight: float
    adjusted_score: float
    filtered: bool
    explanation: str


@dataclass(frozen=True, slots=True)
class WeightUpdateResult:
    repo: str
    category: str
    label: str
    old_weight: float
    new_weight: float
    accepted_count: int
    rejected_count: int
    unknown_count: int
    explanation: str


@dataclass(frozen=True, slots=True)
class Critique:
    quality: float
    message: str
    issues: Sequence[str] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


# A candidate of type T is serialized to a stable str for hashing/persistence.
CandidateSerializer = Callable[[T], str]
# generator(current_candidate, last_critique, next_iteration_index) -> new_candidate
Generator = Callable[[T, "Critique", int], T]
# critic(candidate) -> Critique
Critic = Callable[[T], "Critique"]
# decompose(candidate) -> ordered parts; recompose(original, refined_parts) -> candidate
PartDecomposer = Callable[[T], Sequence["RefinementPart[T]"]]
PartRecomposer = Callable[[T, Sequence["RefinedPart[T]"]], T]
QualityAggregator = Callable[[float, Sequence["RecursiveRefinementNode[T]"]], float]


@dataclass(frozen=True, slots=True)
class RefinementConfig:
    max_iterations: int = 5
    quality_threshold: float = 0.90
    min_delta: float = 0.01
    patience: int = 2
    oscillation_window: int = 4
    require_monotonic: bool = True


@dataclass(frozen=True, slots=True)
class RefinementIteration(Generic[T]):
    iteration: int
    candidate: T
    candidate_hash: str
    critique: Critique
    accepted: bool


@dataclass(frozen=True, slots=True)
class RefinementResult(Generic[T]):
    initial_candidate: T
    final_candidate: T
    final_quality: float
    stop_reason: RefinementStopReason
    iterations: Sequence[RefinementIteration[T]]


@dataclass(frozen=True, slots=True)
class RefinementPart(Generic[T]):
    """One decomposed piece of a candidate fed to recursive refinement."""

    value: T
    key: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RecursiveRefinementNode(Generic[T]):
    """One node in the recursive refinement tree.

    ``path`` is the index lineage from the root (root = ``()``). ``refinement``
    is this node's authoritative flat refinement (post-recompose for an internal
    node, the only refinement for a leaf). ``pre_refinement`` is the extra flat
    refinement an internal node runs BEFORE decomposition (to choose the
    decomposition input); it is ``None`` for leaves and no-decomposition nodes.
    ``children`` are the recursively refined parts; ``aggregate_quality`` folds
    this node + descendants. Iteration accounting (``total_iterations``) counts
    BOTH ``refinement`` and ``pre_refinement``.
    """

    path: tuple[int, ...]
    depth: int
    initial_candidate: T
    final_candidate: T
    refinement: RefinementResult[T]
    pre_refinement: RefinementResult[T] | None = None
    children: tuple["RecursiveRefinementNode[T]", ...] = ()
    aggregate_quality: float = 0.0
    max_depth_reached: bool = False


@dataclass(frozen=True, slots=True)
class RefinedPart(Generic[T]):
    """A decomposed part paired with the node produced by refining it."""

    part: RefinementPart[T]
    node: RecursiveRefinementNode[T]


@dataclass(frozen=True, slots=True)
class RecursiveRefinementResult(Generic[T]):
    initial_candidate: T
    final_candidate: T
    final_quality: float
    tree: RecursiveRefinementNode[T]
    total_iterations: int
    max_observed_depth: int
