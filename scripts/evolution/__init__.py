"""Recursive regression & evolution logic for the pr-agent fork.

Fork-owned package (must NOT import or modify the upstream ``pr_agent`` tree
beyond treating its outputs as plain input data). Provides three deterministic,
unit-testable services:

1. Regression detection  -- persist fingerprinted review findings per repo and
   flag when a previously closed finding reappears.
2. Evolutionary scoring  -- track accepted/rejected code suggestions and evolve
   a bounded, explainable per-(repo, category, label) weight.
3. Recursive self-refinement -- iterate candidate -> critique -> regenerate with
   convergence and anti-oscillation guards.
"""

from scripts.evolution.errors import (
    DuplicateOutcomeError,
    EvolutionError,
    FingerprintCollisionError,
    ValidationError,
)
from scripts.evolution.facade import EvolutionEngine
from scripts.evolution.models import (
    AdjustedSuggestion,
    CandidateSerializer,
    Critic,
Critique,
FindingEventType,
FindingIdentity,
    FindingStatus,
    Generator,
    PartDecomposer,
    PartRecomposer,
    PullRequestContext,
    QualityAggregator,
    RecursiveRefinementNode,
    RecursiveRefinementResult,
    RefinedPart,
RefinementConfig,
    RefinementIteration,
    RefinementPart,
RefinementResult,
RefinementStopReason,
RegressionMatch,
ReviewFinding,
Suggestion,
SuggestionOutcome,
WeightUpdateResult,
)
from scripts.evolution.refinement import (
    RecursiveRefiner,
    SelfRefinementLoop,
    default_candidate_serializer,
)
from scripts.evolution.regression import RegressionDetector
from scripts.evolution.scoring import EvolutionScorer
from scripts.evolution.storage import EvolutionStore

__all__ = [
    "AdjustedSuggestion",
    "CandidateSerializer",
    "Critic",
    "Critique",
    "DuplicateOutcomeError",
    "EvolutionError",
    "EvolutionEngine",
    "EvolutionScorer",
    "EvolutionStore",
    "Generator",
    "FindingEventType",
    "FindingIdentity",
    "FindingStatus",
    "FingerprintCollisionError",
    "PartDecomposer",
    "PartRecomposer",
    "PullRequestContext",
    "QualityAggregator",
    "RecursiveRefiner",
    "RecursiveRefinementNode",
    "RecursiveRefinementResult",
    "RefinedPart",
    "RefinementConfig",
    "RefinementIteration",
    "RefinementPart",
    "RefinementResult",
    "RefinementStopReason",
    "RegressionMatch",
    "RegressionDetector",
    "SelfRefinementLoop",
    "ReviewFinding",
    "Suggestion",
    "SuggestionOutcome",
    "ValidationError",
    "WeightUpdateResult",
    "default_candidate_serializer",
]
