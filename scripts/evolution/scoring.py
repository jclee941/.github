"""Evolutionary scoring: deterministic, explainable suggestion-weight evolution.

Authors accept or reject code suggestions over time. We evolve a bounded weight
per ``(repo, category, label)`` bucket using a simple additive rule (NOT gradient
descent / ML) so every change is explainable:

    accepted  -> weight += 0.05
    rejected  -> weight -= 0.05
    unknown   -> decay 0.01 toward the neutral 1.0
    weight is clamped to [0.5, 1.5]

A suggestion's adjusted score is ``clamp(original_score * weight, 0, 10)`` and is
optionally filtered out below a caller-provided threshold.
"""

from __future__ import annotations

from collections.abc import Sequence

from scripts.evolution.errors import DuplicateOutcomeError, ValidationError
from scripts.evolution.fingerprint import normalize_text, suggestion_fingerprint
from scripts.evolution.models import (
    AdjustedSuggestion,
    PullRequestContext,
    Suggestion,
    SuggestionOutcome,
    WeightUpdateResult,
)
from scripts.evolution.storage import EvolutionStore


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class EvolutionScorer:
    def __init__(
        self,
        store: EvolutionStore,
        *,
        default_weight: float = 1.0,
        min_weight: float = 0.5,
        max_weight: float = 1.5,
        accept_step: float = 0.05,
        reject_step: float = 0.05,
        decay_to_neutral: float = 0.01,
    ) -> None:
        self.store = store
        self.default_weight = default_weight
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.accept_step = accept_step
        self.reject_step = reject_step
        self.decay_to_neutral = decay_to_neutral

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _bucket(suggestion: Suggestion) -> tuple[str, str]:
        category = (suggestion.category or "").strip().lower()
        label = (suggestion.label or "").strip().lower()
        return category, label

    @staticmethod
    def _validate(suggestion: Suggestion) -> None:
        if not suggestion.category or not suggestion.category.strip():
            raise ValidationError("suggestion.category is required")
        if not isinstance(suggestion.score, (int, float)):
            raise ValidationError("suggestion.score must be numeric")
        if suggestion.score < 0 or suggestion.score > 10:
            raise ValidationError("suggestion.score must be within [0, 10]")

    def _current_weight(self, repo: str, category: str, label: str) -> float:
        row = self.store.get_weight(repo, category, label)
        return float(row["weight"]) if row is not None else self.default_weight

    # -- scoring --------------------------------------------------------------
    def adjust_suggestion(
        self,
        repo: str,
        suggestion: Suggestion,
        *,
        filter_threshold: float = 0.0,
    ) -> AdjustedSuggestion:
        if not repo or not repo.strip():
            raise ValidationError("repo is required")
        self._validate(suggestion)

        category, label = self._bucket(suggestion)
        weight = self._current_weight(repo, category, label)
        adjusted = _clamp(suggestion.score * weight, 0.0, 10.0)
        filtered = adjusted < filter_threshold

        if weight == 1.0:
            explanation = "neutral weight 1.0 (no history)"
        else:
            explanation = (
                f"weight {weight:.2f} for ({category}|{label}): "
                f"{suggestion.score:.2f} -> {adjusted:.2f}"
            )
        return AdjustedSuggestion(
            suggestion=suggestion,
            weight=weight,
            adjusted_score=adjusted,
            filtered=filtered,
            explanation=explanation,
        )

    def adjust_suggestions(
        self,
        repo: str,
        suggestions: Sequence[Suggestion],
        *,
        filter_threshold: float = 0.0,
    ) -> list[AdjustedSuggestion]:
        adjusted = [self.adjust_suggestion(repo, s, filter_threshold=filter_threshold) for s in suggestions]
        adjusted.sort(
            key=lambda a: (
                a.filtered,                        # unfiltered (False) first
                -a.adjusted_score,                 # higher adjusted score first
                -a.suggestion.score,               # higher original score first
                a.suggestion.suggestion_id,        # stable tiebreak
            )
        )
        return adjusted

    # -- weight evolution -----------------------------------------------------
    def _next_weight(self, old_weight: float, outcome: SuggestionOutcome) -> tuple[float, str]:
        if outcome == SuggestionOutcome.ACCEPTED:
            raw = old_weight + self.accept_step
            explanation = f"accepted: +{self.accept_step:.2f}"
        elif outcome == SuggestionOutcome.REJECTED:
            raw = old_weight - self.reject_step
            explanation = f"rejected: -{self.reject_step:.2f}"
        else:  # UNKNOWN -> decay toward neutral
            if old_weight > 1.0:
                raw = max(1.0, old_weight - self.decay_to_neutral)
                explanation = f"unknown: decay toward neutral -{self.decay_to_neutral:.2f}"
            elif old_weight < 1.0:
                raw = min(1.0, old_weight + self.decay_to_neutral)
                explanation = f"unknown: decay toward neutral +{self.decay_to_neutral:.2f}"
            else:
                raw = 1.0
                explanation = "unknown: already neutral"

        new_weight = round(_clamp(raw, self.min_weight, self.max_weight), 4)
        if new_weight != round(raw, 4):
            explanation += f"; clamped to {new_weight:.2f}"
        return new_weight, explanation

    def _compute_weight_update(
        self,
        repo: str,
        category: str,
        label: str,
        outcome: SuggestionOutcome,
    ) -> WeightUpdateResult:
        """Pure computation of the next weight (no write). Used by the standalone
        update_weight(); record_outcome() uses the store's atomic apply_outcome()."""
        category = (category or "").strip().lower()
        label = (label or "").strip().lower()
        row = self.store.get_weight(repo, category, label)
        old_weight = float(row["weight"]) if row is not None else self.default_weight
        accepted = int(row["accepted_count"]) if row is not None else 0
        rejected = int(row["rejected_count"]) if row is not None else 0
        unknown = int(row["unknown_count"]) if row is not None else 0

        new_weight, explanation = self._next_weight(old_weight, outcome)
        if outcome == SuggestionOutcome.ACCEPTED:
            accepted += 1
        elif outcome == SuggestionOutcome.REJECTED:
            rejected += 1
        else:
            unknown += 1

        return WeightUpdateResult(
            repo=repo,
            category=category,
            label=label,
            old_weight=old_weight,
            new_weight=new_weight,
            accepted_count=accepted,
            rejected_count=rejected,
            unknown_count=unknown,
            explanation=explanation,
        )

    def update_weight(
        self,
        repo: str,
        category: str,
        label: str,
        outcome: SuggestionOutcome,
    ) -> WeightUpdateResult:
        result = self._compute_weight_update(repo, category, label, outcome)
        self.store.upsert_weight(result, outcome)
        return result

    def record_outcome(
        self,
        ctx: PullRequestContext,
        suggestion: Suggestion,
        outcome: SuggestionOutcome,
        *,
        adjusted_score: float | None = None,
        outcome_source: str = "author",
    ) -> WeightUpdateResult:
        """Record an author's accept/reject and evolve the bucket weight.

        Idempotent for an identical (suggestion_id, outcome); raises
        ``DuplicateOutcomeError`` if the same suggestion is later recorded with a
        conflicting outcome.
        """
        if not ctx.repo or not ctx.repo.strip():
            raise ValidationError("repo is required")
        self._validate(suggestion)

        category, label = self._bucket(suggestion)

        if adjusted_score is None:
            adjusted_score = self.adjust_suggestion(ctx.repo, suggestion).adjusted_score

        # The ENTIRE read-modify-write (existing-outcome check, current-weight
        # read, next-weight computation, outcome insert, weight upsert) runs
        # inside ONE BEGIN IMMEDIATE transaction in the store (D7). We pass our
        # pure weight rule as a callback so it is evaluated against the LOCKED
        # current weight, never a stale pre-lock read.
        info = self.store.apply_outcome(
            ctx,
            suggestion,
            adjusted_score,
            outcome,
            category,
            label,
            self._next_weight,
            suggestion_fingerprint=suggestion_fingerprint(ctx.repo, suggestion),
            normalized_text=normalize_text(suggestion.text),
            outcome_source=outcome_source,
            default_weight=self.default_weight,
        )

        if info["status"] == "conflict":
            raise DuplicateOutcomeError(
                ctx.repo, suggestion.suggestion_id,
                str(info["conflict_existing"]), str(outcome),
            )

        return WeightUpdateResult(
            repo=ctx.repo,
            category=category,
            label=label,
            old_weight=float(info["old_weight"]),
            new_weight=float(info["new_weight"]),
            accepted_count=int(info["accepted_count"]),
            rejected_count=int(info["rejected_count"]),
            unknown_count=int(info["unknown_count"]),
            explanation=str(info["explanation"]),
        )
