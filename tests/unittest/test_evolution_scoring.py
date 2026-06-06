"""Tests for scripts/evolution/scoring.py (EvolutionScorer)."""

from __future__ import annotations

import pytest

from scripts.evolution.errors import DuplicateOutcomeError, ValidationError
from scripts.evolution.models import PullRequestContext, Suggestion, SuggestionOutcome
from scripts.evolution.scoring import EvolutionScorer
from scripts.evolution.storage import EvolutionStore


@pytest.fixture
def scorer() -> EvolutionScorer:
    store = EvolutionStore(":memory:")
    store.initialize()
    return EvolutionScorer(store)


def _s(sid="s1", category="performance", label="perf", text="use a set", score=8.0) -> Suggestion:
    return Suggestion(sid, category, label, text, score, "f.py", 1, 2)


def _ctx() -> PullRequestContext:
    return PullRequestContext("repo", "url", 1)


class TestAdjustNoHistory:
    def test_default_weight_is_one(self, scorer):
        adj = scorer.adjust_suggestion("repo", _s(score=8.0))
        assert adj.weight == 1.0
        assert adj.adjusted_score == 8.0
        assert adj.filtered is False
        assert "1.0" in adj.explanation or "neutral" in adj.explanation.lower()


class TestWeightUpdateRule:
    def test_accept_increases_weight(self, scorer):
        r = scorer.record_outcome(_ctx(), _s(), SuggestionOutcome.ACCEPTED)
        assert abs(r.new_weight - 1.05) < 1e-9
        assert "accepted" in r.explanation.lower()

    def test_reject_decreases_weight(self, scorer):
        r = scorer.record_outcome(_ctx(), _s(), SuggestionOutcome.REJECTED)
        assert abs(r.new_weight - 0.95) < 1e-9
        assert "rejected" in r.explanation.lower()

    def test_unknown_decays_toward_neutral_from_above(self, scorer):
        for i in range(3):  # push weight above 1.0
            scorer.record_outcome(_ctx(), _s(sid=f"a{i}"), SuggestionOutcome.ACCEPTED)
        before = scorer.store.get_weight("repo", "performance", "perf")["weight"]
        r = scorer.record_outcome(_ctx(), _s(sid="u1"), SuggestionOutcome.UNKNOWN)
        assert r.new_weight < before
        assert r.new_weight >= 1.0

    def test_unknown_decays_toward_neutral_from_below(self, scorer):
        for i in range(3):
            scorer.record_outcome(_ctx(), _s(sid=f"r{i}"), SuggestionOutcome.REJECTED)
        before = scorer.store.get_weight("repo", "performance", "perf")["weight"]
        r = scorer.record_outcome(_ctx(), _s(sid="u1"), SuggestionOutcome.UNKNOWN)
        assert r.new_weight > before
        assert r.new_weight <= 1.0

    def test_weight_saturates_at_max(self, scorer):
        for i in range(50):
            r = scorer.record_outcome(_ctx(), _s(sid=f"a{i}"), SuggestionOutcome.ACCEPTED)
        assert r.new_weight == 1.5

    def test_weight_saturates_at_min(self, scorer):
        for i in range(50):
            r = scorer.record_outcome(_ctx(), _s(sid=f"r{i}"), SuggestionOutcome.REJECTED)
        assert r.new_weight == 0.5


class TestScoreAdjustment:
    def test_adjusted_score_uses_weight(self, scorer):
        scorer.record_outcome(_ctx(), _s(sid="a0"), SuggestionOutcome.ACCEPTED)  # weight 1.05
        adj = scorer.adjust_suggestion("repo", _s(score=8.0))
        assert abs(adj.adjusted_score - 8.4) < 1e-9

    def test_adjusted_score_clamps_to_ten(self, scorer):
        for i in range(50):  # weight -> 1.5
            scorer.record_outcome(_ctx(), _s(sid=f"a{i}"), SuggestionOutcome.ACCEPTED)
        adj = scorer.adjust_suggestion("repo", _s(score=9.0))  # 9*1.5=13.5 -> clamp 10
        assert adj.adjusted_score == 10.0

    def test_filter_uses_adjusted_not_original(self, scorer):
        for i in range(50):  # weight -> 0.5
            scorer.record_outcome(_ctx(), _s(sid=f"r{i}"), SuggestionOutcome.REJECTED)
        # original 7.0 passes a 5.0 threshold, but adjusted 3.5 does not
        adj = scorer.adjust_suggestion("repo", _s(score=7.0), filter_threshold=5.0)
        assert abs(adj.adjusted_score - 3.5) < 1e-9
        assert adj.filtered is True


class TestBatchSortAndNormalization:
    def test_sort_is_deterministic_unfiltered_first_then_score(self, scorer):
        suggestions = [
            _s(sid="low", text="a", score=3.0),
            _s(sid="high", text="b", score=9.0),
            _s(sid="mid", text="c", score=6.0),
        ]
        out = scorer.adjust_suggestions("repo", suggestions, filter_threshold=5.0)
        ids = [a.suggestion.suggestion_id for a in out]
        # unfiltered (>=5 adjusted) first by score desc, filtered last
        assert ids == ["high", "mid", "low"]
        assert out[-1].filtered is True

    def test_category_label_normalized_for_weight_key(self, scorer):
        # Record with mixed case / whitespace; lookup with canonical form must hit same bucket
        scorer.record_outcome(_ctx(), Suggestion("x", "  Performance ", "  Perf ", "t", 5.0), SuggestionOutcome.ACCEPTED)
        row = scorer.store.get_weight("repo", "performance", "perf")
        assert row is not None
        assert abs(row["weight"] - 1.05) < 1e-9

    def test_empty_label_maps_to_empty_string_bucket(self, scorer):
        scorer.record_outcome(_ctx(), Suggestion("x", "bug", "", "t", 5.0), SuggestionOutcome.ACCEPTED)
        assert scorer.store.get_weight("repo", "bug", "") is not None


class TestValidationAndIdempotency:
    def test_negative_score_raises(self, scorer):
        with pytest.raises(ValidationError):
            scorer.adjust_suggestion("repo", _s(score=-1.0))

    def test_score_above_ten_raises(self, scorer):
        with pytest.raises(ValidationError):
            scorer.adjust_suggestion("repo", _s(score=11.0))

    def test_empty_category_raises(self, scorer):
        with pytest.raises(ValidationError):
            scorer.adjust_suggestion("repo", Suggestion("x", "", "l", "t", 5.0))

    def test_same_outcome_recorded_twice_is_idempotent(self, scorer):
        scorer.record_outcome(_ctx(), _s(sid="dup"), SuggestionOutcome.ACCEPTED)
        # same suggestion_id + same outcome -> no double weight change
        before = scorer.store.get_weight("repo", "performance", "perf")["weight"]
        scorer.record_outcome(_ctx(), _s(sid="dup"), SuggestionOutcome.ACCEPTED)
        after = scorer.store.get_weight("repo", "performance", "perf")["weight"]
        assert before == after

    def test_conflicting_outcome_raises(self, scorer):
        scorer.record_outcome(_ctx(), _s(sid="dup"), SuggestionOutcome.ACCEPTED)
        with pytest.raises(DuplicateOutcomeError):
            scorer.record_outcome(_ctx(), _s(sid="dup"), SuggestionOutcome.REJECTED)

    def test_idempotent_replay_does_not_double_count(self, scorer):
        # D7: replaying the SAME (suggestion_id, outcome) must not increment the
        # accepted_count nor change the weight.
        scorer.record_outcome(_ctx(), _s(sid="dup"), SuggestionOutcome.ACCEPTED)
        row1 = scorer.store.get_weight("repo", "performance", "perf")
        scorer.record_outcome(_ctx(), _s(sid="dup"), SuggestionOutcome.ACCEPTED)
        row2 = scorer.store.get_weight("repo", "performance", "perf")
        assert row1["accepted_count"] == row2["accepted_count"] == 1
        assert row1["weight"] == row2["weight"]


class TestAtomicSerialization:
    def test_sequential_distinct_outcomes_apply_from_locked_state(self, tmp_path):
        # D7: two store instances on the SAME file DB (separate connections).
        # Each record_outcome must compute from the committed current weight, so
        # two accepts in the same bucket land at 1.10 with accepted_count 2 
        # (NOT 1.05/1 from a stale pre-lock read).
        db = tmp_path / "ev.sqlite"
        s0 = EvolutionStore(str(db), timeout_seconds=5.0)
        s0.initialize()
        sc1 = EvolutionScorer(EvolutionStore(str(db), timeout_seconds=5.0))
        sc2 = EvolutionScorer(EvolutionStore(str(db), timeout_seconds=5.0))
        sc1.record_outcome(_ctx(), _s(sid="a1"), SuggestionOutcome.ACCEPTED)
        sc2.record_outcome(_ctx(), _s(sid="a2"), SuggestionOutcome.ACCEPTED)
        row = s0.get_weight("repo", "performance", "perf")
        assert row["accepted_count"] == 2
        assert abs(row["weight"] - 1.10) < 1e-9


class TestCustomDefaultWeight:
    def test_record_outcome_starts_from_custom_default_weight(self, tmp_path):
        # A scorer configured with a non-1.0 default_weight must apply the first
        # outcome on top of THAT default, not a hardcoded 1.0.
        store = EvolutionStore(":memory:")
        store.initialize()
        scorer = EvolutionScorer(store, default_weight=1.2)
        r = scorer.record_outcome(_ctx(), _s(sid="c1"), SuggestionOutcome.ACCEPTED)
        # 1.2 + 0.05 accept step = 1.25
        assert abs(r.old_weight - 1.2) < 1e-9
        assert abs(r.new_weight - 1.25) < 1e-9
        row = store.get_weight("repo", "performance", "perf")
        assert abs(row["weight"] - 1.25) < 1e-9

    def test_adjust_suggestion_uses_custom_default_weight(self, tmp_path):
        store = EvolutionStore(":memory:")
        store.initialize()
        scorer = EvolutionScorer(store, default_weight=1.2)
        adj = scorer.adjust_suggestion("repo", _s(score=5.0))
        # no history -> uses custom default 1.2 -> 5.0 * 1.2 = 6.0
        assert abs(adj.weight - 1.2) < 1e-9
        assert abs(adj.adjusted_score - 6.0) < 1e-9
