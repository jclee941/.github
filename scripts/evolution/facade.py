"""Thin orchestration facade over the evolution services.

``EvolutionEngine`` wires together the storage layer, the regression detector,
the evolution scorer and the self-refinement loop. It contains no business logic
of its own -- it only delegates and (optionally) persists refinement runs.
"""

from __future__ import annotations

from collections.abc import Sequence

from scripts.evolution.models import (
    AdjustedSuggestion,
    CandidateSerializer,
Critic,
    Generator,
    PartDecomposer,
    PartRecomposer,
    PullRequestContext,
    RecursiveRefinementResult,
RefinementConfig,
RefinementResult,
RegressionMatch,
ReviewFinding,
Suggestion,
    SuggestionOutcome,
    T,
WeightUpdateResult,
)
from scripts.evolution.refinement import RecursiveRefiner, SelfRefinementLoop
from scripts.evolution.regression import RegressionDetector
from scripts.evolution.scoring import EvolutionScorer
from scripts.evolution.storage import EvolutionStore


class EvolutionEngine:
    def __init__(self, store: EvolutionStore) -> None:
        self.store = store
        self.regression = RegressionDetector(store)
        self.scoring = EvolutionScorer(store)
        self.refinement = SelfRefinementLoop()

    def process_review_findings(
        self,
        ctx: PullRequestContext,
        findings: Sequence[ReviewFinding],
    ) -> list[RegressionMatch]:
        return self.regression.ingest_findings(ctx, findings)

    def adjust_code_suggestions(
        self,
        repo: str,
        suggestions: Sequence[Suggestion],
        *,
        filter_threshold: float = 0.0,
    ) -> list[AdjustedSuggestion]:
        return self.scoring.adjust_suggestions(repo, suggestions, filter_threshold=filter_threshold)

    def record_suggestion_outcomes(
        self,
        ctx: PullRequestContext,
        outcomes: Sequence[tuple[Suggestion, SuggestionOutcome]],
        *,
        outcome_source: str = "author",
    ) -> list[WeightUpdateResult]:
        return [
            self.scoring.record_outcome(ctx, suggestion, outcome, outcome_source=outcome_source)
            for suggestion, outcome in outcomes
        ]

    def refine_output(
        self,
        initial_candidate: str,
        critic: Critic,
        generator: Generator,
        config: RefinementConfig = RefinementConfig(),
        *,
        run_id: str | None = None,
        persist: bool = False,
        repo: str | None = None,
        pr_url: str | None = None,
    ) -> RefinementResult:
        result = self.refinement.refine(initial_candidate, critic, generator, config)
        if persist:
            self.store.record_refinement_run(
                run_id or EvolutionStore.new_run_id(),
                result,
                config,
                repo=repo,
                pr_url=pr_url,
            )
        return result

    def refine_recursive(
        self,
        initial_candidate: T,
        critic: Critic[T],
        generator: Generator[T],
        decompose: PartDecomposer[T],
        recompose: PartRecomposer[T],
        config: RefinementConfig = RefinementConfig(),
        *,
        serializer: CandidateSerializer[T] | None = None,
        max_depth: int = 1,
        max_workers: int = 1,
        run_id: str | None = None,
        persist: bool = False,
        repo: str | None = None,
        pr_url: str | None = None,
    ) -> RecursiveRefinementResult[T]:
        refiner: RecursiveRefiner[T] = RecursiveRefiner(serializer=serializer, max_workers=max_workers)
        result = refiner.refine_recursive(
            initial_candidate, critic, generator, decompose, recompose, config,
            max_depth=max_depth,
        )
        if persist:
            self.store.record_recursive_refinement_run(
                run_id or EvolutionStore.new_run_id(),
                result,
                config,
                repo=repo,
                pr_url=pr_url,
                candidate_serializer=serializer,
            )
        return result
