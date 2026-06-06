"""Property-based verification of scripts/evolution/ invariants (검증 고도화).

Uses Hypothesis to assert universal invariants across randomized inputs:
  P1 evolutionary scoring  -- weight always in [0.5, 1.5], 4dp; counts coherent;
                              exact additive model; adjusted score in [0, 10].
  P2 self-refinement       -- always terminates within max_iterations+1 recorded
                              iterations; returns the absolute-best candidate it
                              saw; valid stop reason; never raises for valid input.
  P3 fingerprint           -- deterministic; correct hex shape; title excluded;
                              marker-field changes change the digest; validation.

Hypothesis is an optional dev dependency (requirements-dev.txt). The whole module
skips cleanly where it is not installed so lean CI environments are unaffected.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from scripts.evolution.errors import ValidationError  # noqa: E402
from scripts.evolution.fingerprint import finding_identity  # noqa: E402
from scripts.evolution.models import (  # noqa: E402
    Critique,
    PullRequestContext,
    RefinementConfig,
    RefinementStopReason,
    ReviewFinding,
    Suggestion,
    SuggestionOutcome,
)
from scripts.evolution.refinement import SelfRefinementLoop  # noqa: E402
from scripts.evolution.scoring import EvolutionScorer  # noqa: E402
from scripts.evolution.storage import EvolutionStore  # noqa: E402


def _num(row: Mapping[str, Any], key: str) -> float:
    """Read a numeric column from a sqlite Row/Mapping as float (type-clean)."""
    return float(row[key])

# --------------------------------------------------------------------------- #
# P1 — evolutionary scoring invariants
# --------------------------------------------------------------------------- #
_OUTCOMES = st.sampled_from(
    [SuggestionOutcome.ACCEPTED, SuggestionOutcome.REJECTED, SuggestionOutcome.UNKNOWN]
)


def _model_weight(weight: float, outcome: SuggestionOutcome) -> float:
    """Independent re-implementation of the additive weight rule (oracle)."""
    if outcome == SuggestionOutcome.ACCEPTED:
        raw = weight + 0.05
    elif outcome == SuggestionOutcome.REJECTED:
        raw = weight - 0.05
    else:  # UNKNOWN -> decay toward neutral 1.0
        if weight > 1.0:
            raw = max(1.0, weight - 0.01)
        elif weight < 1.0:
            raw = min(1.0, weight + 0.01)
        else:
            raw = 1.0
    return round(max(0.5, min(1.5, raw)), 4)


def _suggestion(sid: str, score: float = 5.0) -> Suggestion:
    return Suggestion(sid, "performance", "perf", "use a set", score, "f.py", 1, 2)


class TestWeightInvariants:
    @settings(deadline=None, max_examples=80)
    @given(outcomes=st.lists(_OUTCOMES, min_size=0, max_size=60))
    def test_weight_stays_in_bounds_and_matches_model(self, outcomes):
        store = EvolutionStore(":memory:")
        store.initialize()
        scorer = EvolutionScorer(store)
        ctx = PullRequestContext("repo", "url", 1)

        for i, outcome in enumerate(outcomes):
            scorer.record_outcome(ctx, _suggestion(f"s{i}"), outcome)

        row = store.get_weight("repo", "performance", "perf")
        if not outcomes:
            assert row is None
            return
        assert row is not None  # narrow for type-checker after the early return

        # bounds + rounding invariant
        weight = _num(row, "weight")
        assert 0.5 <= weight <= 1.5
        assert weight == round(weight, 4)
        # counts coherence
        assert (
            _num(row, "accepted_count") + _num(row, "rejected_count") + _num(row, "unknown_count")
            == len(outcomes)
        )
        assert _num(row, "total_updates") == len(outcomes)

        # exact additive model
        expected = 1.0
        for outcome in outcomes:
            expected = _model_weight(expected, outcome)
        assert weight == pytest.approx(expected)

    @settings(deadline=None, max_examples=60)
    @given(score=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False))
    def test_adjusted_score_in_bounds(self, score):
        store = EvolutionStore(":memory:")
        store.initialize()
        scorer = EvolutionScorer(store)
        adj = scorer.adjust_suggestion("repo", _suggestion("x", score))
        assert 0.0 <= adj.adjusted_score <= 10.0
        assert adj.adjusted_score == pytest.approx(max(0.0, min(10.0, score * adj.weight)))


# --------------------------------------------------------------------------- #
# P2 — self-refinement invariants
# --------------------------------------------------------------------------- #
_CANDIDATE = st.text(min_size=0, max_size=20)


def _make_critic(quality_map: dict[str, float]):
    """Deterministic critic: quality is a stable function of the candidate text."""
    def _default(candidate: str) -> float:
        return (sum(ord(c) for c in candidate) % 101) / 100.0

    def _critic(candidate: str) -> Critique:
        q = quality_map.get(candidate, _default(candidate))
        return Critique(quality=q, message="q")

    return _critic


def _make_generator(sequence: list[str]):
    """Valid generator: always returns a str picked from a finite sequence."""
    def _gen(candidate: str, critique: Critique, iteration: int) -> str:
        return sequence[(iteration - 1) % len(sequence)]

    return _gen


class TestRefinementInvariants:
    @settings(deadline=None, max_examples=120)
    @given(
        initial=_CANDIDATE,
        sequence=st.lists(_CANDIDATE, min_size=1, max_size=8),
        quality_map=st.dictionaries(
            keys=_CANDIDATE,
            values=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            max_size=20,
        ),
        max_iterations=st.integers(min_value=1, max_value=8),
        threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_delta=st.floats(min_value=0.0, max_value=0.2, allow_nan=False, allow_infinity=False),
        patience=st.integers(min_value=1, max_value=5),
        oscillation_window=st.integers(min_value=2, max_value=6),
        require_monotonic=st.booleans(),
    )
    def test_refine_universal_invariants(
        self,
        initial,
        sequence,
        quality_map,
        max_iterations,
        threshold,
        min_delta,
        patience,
        oscillation_window,
        require_monotonic,
    ):
        loop = SelfRefinementLoop()
        critic = _make_critic(quality_map)
        generator = _make_generator(sequence)
        config = RefinementConfig(
            max_iterations=max_iterations,
            quality_threshold=threshold,
            min_delta=min_delta,
            patience=patience,
            oscillation_window=oscillation_window,
            require_monotonic=require_monotonic,
        )

        result = loop.refine(initial, critic, generator, config)

        # valid stop reason
        assert isinstance(result.stop_reason, RefinementStopReason)
        # termination bound: recorded iterations never exceed budget+1
        assert 1 <= len(result.iterations) <= config.max_iterations + 1
        # all critiques are valid qualities
        assert all(0.0 <= it.critique.quality <= 1.0 for it in result.iterations)

        recorded_qualities = [it.critique.quality for it in result.iterations]
        recorded_candidates = [it.candidate for it in result.iterations]

        # absolute-best: final quality equals the max quality actually seen
        assert result.final_quality == pytest.approx(max(recorded_qualities))
        # final candidate is one that appeared, AND appears with the final quality
        assert result.final_candidate in recorded_candidates
        assert any(
            it.candidate == result.final_candidate
            and it.critique.quality == pytest.approx(result.final_quality)
            for it in result.iterations
        )


# --------------------------------------------------------------------------- #
# P3 — fingerprint invariants
# --------------------------------------------------------------------------- #
_NONEMPTY = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())
_TEXT = st.text(min_size=0, max_size=50)


class TestFingerprintInvariants:
    @settings(deadline=None, max_examples=150)
    @given(
        repo=_NONEMPTY,
        category=_NONEMPTY,
        title=_TEXT,
        content=_TEXT,
        file_path=_TEXT,
        start=st.integers(min_value=0, max_value=10_000),
        length=st.integers(min_value=0, max_value=200),
    )
    def test_deterministic_and_well_formed(self, repo, category, title, content, file_path, start, length):
        finding = ReviewFinding(category, "high", title, content, file_path, start, start + length)
        id1 = finding_identity(repo, finding)
        id2 = finding_identity(repo, finding)
        # determinism
        assert id1 == id2
        # shape
        assert re.fullmatch(r"[0-9a-f]{16}", id1.fingerprint)
        assert re.fullmatch(r"[0-9a-f]{64}", id1.fingerprint_full)
        assert id1.fingerprint == id1.fingerprint_full[:16]

    @settings(deadline=None, max_examples=80)
    @given(
        repo=_NONEMPTY,
        category=_NONEMPTY,
        content=_TEXT,
        file_path=_TEXT,
        start=st.integers(min_value=0, max_value=1000),
        length=st.integers(min_value=0, max_value=50),
        title_a=_TEXT,
        title_b=_TEXT,
    )
    def test_title_excluded_from_fingerprint(self, repo, category, content, file_path, start, length, title_a, title_b):
        end = start + length
        fa = ReviewFinding(category, "high", title_a, content, file_path, start, end)
        fb = ReviewFinding(category, "high", title_b, content, file_path, start, end)
        assert finding_identity(repo, fa).fingerprint_full == finding_identity(repo, fb).fingerprint_full

    @settings(deadline=None, max_examples=120)
    @given(
        repo=_NONEMPTY,
        category=_NONEMPTY,
        content_a=_TEXT,
        content_b=_TEXT,
        file_path=_TEXT,
        start=st.integers(min_value=0, max_value=1000),
        length=st.integers(min_value=0, max_value=50),
    )
    def test_content_change_changes_digest(self, repo, category, content_a, content_b, file_path, start, length):
        # When content (a marker field) differs, the marker input differs and the
        # full SHA-256 digest differs (collision-resistant).
        if content_a == content_b:
            return  # only meaningful when content actually differs
        end = start + length
        fa = ReviewFinding(category, "high", "t", content_a, file_path, start, end)
        fb = ReviewFinding(category, "high", "t", content_b, file_path, start, end)
        ida = finding_identity(repo, fa)
        idb = finding_identity(repo, fb)
        assert ida.marker_input != idb.marker_input
        assert ida.fingerprint_full != idb.fingerprint_full

    @settings(deadline=None, max_examples=40)
    @given(category=_NONEMPTY, content=_TEXT)
    def test_empty_repo_raises(self, category, content):
        with pytest.raises(ValidationError):
            finding_identity("", ReviewFinding(category, "high", "t", content, "f.py", 1, 2))

    @settings(deadline=None, max_examples=40)
    @given(
        repo=_NONEMPTY,
        start=st.integers(min_value=1, max_value=1000),
        delta=st.integers(min_value=1, max_value=500),
    )
    def test_end_before_start_raises(self, repo, start, delta):
        end = start - delta  # strictly less than start, and > 0 stays a real range
        if end < 0:
            end = 0
        if end == 0:
            return  # 0 is the "unset" sentinel, allowed; skip
        with pytest.raises(ValidationError):
            finding_identity(repo, ReviewFinding("bug", "high", "t", "c", "f.py", start, end))


# --------------------------------------------------------------------------- #
# P4 — recursive refinement invariants
# --------------------------------------------------------------------------- #
from scripts.evolution.models import RefinementPart  # noqa: E402
from scripts.evolution.refinement import RecursiveRefiner  # noqa: E402


class TestRecursiveInvariants:
    @settings(deadline=None, max_examples=80)
    @given(
        initial=st.text(min_size=0, max_size=12),
        fanout=st.integers(min_value=0, max_value=3),
        max_depth=st.integers(min_value=0, max_value=3),
        max_iterations=st.integers(min_value=1, max_value=4),
        quality_map=st.dictionaries(
            keys=st.text(min_size=0, max_size=12),
            values=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            max_size=20,
        ),
    )
    def test_recursive_universal_invariants(self, initial, fanout, max_depth, max_iterations, quality_map):
        def _default_q(candidate: str) -> float:
            return (sum(ord(c) for c in candidate) % 101) / 100.0

        def critic(candidate):
            return Critique(quality=quality_map.get(candidate, _default_q(candidate)), message="q")

        def generator(candidate, critique, iteration):
            return candidate + "x"

        def decompose(candidate):
            # Bounded fanout of distinct children so the tree is finite per level;
            # depth is bounded only by max_depth (anti-infinite-recursion guard).
            return [RefinementPart(value=candidate + str(i), key=str(i)) for i in range(fanout)]

        def recompose(original, refined):
            return "|".join(rp.node.final_candidate for rp in refined) or original

        refiner = RecursiveRefiner()
        result = refiner.refine_recursive(
            initial, critic, generator, decompose, recompose,
            RefinementConfig(max_iterations=max_iterations, quality_threshold=1.0),
            max_depth=max_depth,
        )

        # termination + depth bound
        def _walk(node):
            yield node
            for child in node.children:
                yield from _walk(child)

        nodes = list(_walk(result.tree))
        assert all(0 <= n.depth <= max_depth for n in nodes)
        assert result.max_observed_depth == max(n.depth for n in nodes)
        assert result.max_observed_depth <= max_depth
        # total_iterations == sum over all nodes of BOTH the post-recompose
        # refinement and the pre-decompose flat refinement (when present).
        def _node_iters(n):
            total = len(n.refinement.iterations)
            if n.pre_refinement is not None:
                total += len(n.pre_refinement.iterations)
            return total
        assert result.total_iterations == sum(_node_iters(n) for n in nodes)
        # nodes at max_depth never decompose further
        assert all(n.children == () for n in nodes if n.depth == max_depth)
        # zero fanout always yields a single-node tree
        if fanout == 0:
            assert result.tree.children == ()
