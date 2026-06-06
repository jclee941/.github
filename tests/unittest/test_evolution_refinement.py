"""Tests for scripts/evolution/refinement.py (SelfRefinementLoop).

The loop is pure: it takes an initial candidate string, a deterministic
``critic(candidate) -> Critique`` and ``generator(candidate, critique, iteration)
-> str``. No storage, no network, no LLM.
"""

from __future__ import annotations

import pytest

from scripts.evolution.errors import ValidationError
from scripts.evolution.models import Critique, RefinementConfig, RefinementStopReason
from scripts.evolution.refinement import SelfRefinementLoop


def critic_len(scale: float = 50.0):
    """Quality grows with candidate length (bounded to 1.0)."""
    def _critic(candidate: str) -> Critique:
        q = min(1.0, len(candidate) / scale)
        return Critique(quality=q, message=f"len={len(candidate)} quality={q:.3f}")
    return _critic


class TestStopReasons:
    def test_threshold_reached_immediately(self):
        loop = SelfRefinementLoop()
        critic = lambda c: Critique(0.95, "great")  # noqa: E731
        gen = lambda c, cr, i: c + "x"  # noqa: E731
        result = loop.refine("seed", critic, gen, RefinementConfig(quality_threshold=0.9))
        assert result.stop_reason == RefinementStopReason.THRESHOLD_REACHED
        assert result.final_candidate == "seed"
        assert len(result.iterations) == 1

    def test_improves_until_threshold(self):
        loop = SelfRefinementLoop()
        critic = critic_len(scale=10.0)  # need len>=9 for q>=0.9
        gen = lambda c, cr, i: c + "ab"  # noqa: E731
        result = loop.refine("xx", critic, gen, RefinementConfig(quality_threshold=0.9, max_iterations=10))
        assert result.stop_reason == RefinementStopReason.THRESHOLD_REACHED
        assert result.final_quality >= 0.9
        # best candidate is the longest one
        assert len(result.final_candidate) >= 9

    def test_max_iterations(self):
        loop = SelfRefinementLoop()
        critic = critic_len(scale=10000.0)  # never reaches threshold
        gen = lambda c, cr, i: c + "z"  # noqa: E731
        result = loop.refine("a", critic, gen, RefinementConfig(quality_threshold=0.99, max_iterations=3, patience=99))
        assert result.stop_reason == RefinementStopReason.MAX_ITERATIONS
        # iterations recorded: initial + 3 = 4
        assert len(result.iterations) == 4

    def test_generator_stalled_identical_next(self):
        loop = SelfRefinementLoop()
        critic = critic_len(scale=100.0)
        gen = lambda c, cr, i: c  # noqa: E731  generator returns same candidate
        result = loop.refine("seed", critic, gen, RefinementConfig(quality_threshold=0.99))
        assert result.stop_reason == RefinementStopReason.GENERATOR_STALLED

    def test_oscillation_a_b_a(self):
        loop = SelfRefinementLoop()
        # critic gives same quality to A and B so neither is "best improvement"
        def critic(c):
            return Critique(0.4, "flat")
        seq = {"A": "B", "B": "A"}
        gen = lambda c, cr, i: seq[c]  # noqa: E731
        result = loop.refine("A", critic, gen, RefinementConfig(quality_threshold=0.99, patience=99, require_monotonic=False))
        assert result.stop_reason == RefinementStopReason.OSCILLATION_DETECTED

    def test_no_monotonic_improvement_patience(self):
        loop = SelfRefinementLoop()
        # Quality stays flat; never improves by min_delta. With require_monotonic
        # off, distinct candidates keep coming but quality plateaus -> patience.
        counter = {"n": 0}
        def critic(c):
            return Critique(0.5, "flat")
        def gen(c, cr, i):
            counter["n"] += 1
            return c + str(counter["n"])  # always distinct, never duplicate
        result = loop.refine("seed", critic, gen, RefinementConfig(quality_threshold=0.99, patience=2, max_iterations=20, require_monotonic=False))
        assert result.stop_reason == RefinementStopReason.NO_MONOTONIC_IMPROVEMENT

    def test_monotonic_guard_rejects_regressing_next(self):
        loop = SelfRefinementLoop()
        # current quality high, proposed next is much worse -> stop, keep best.
        def critic(c):
            return Critique(0.8 if c == "good" else 0.1, "q")
        gen = lambda c, cr, i: "bad"  # noqa: E731
        result = loop.refine("good", critic, gen, RefinementConfig(quality_threshold=0.99, require_monotonic=True, min_delta=0.01))
        assert result.stop_reason == RefinementStopReason.NO_MONOTONIC_IMPROVEMENT
        assert result.final_candidate == "good"
        assert result.final_quality == 0.8


class TestBestCandidate:
    def test_returns_best_not_last(self):
        loop = SelfRefinementLoop()
        # quality: seed=0.5, then a peak, then decline (require_monotonic off)
        qmap = {"seed": 0.5, "peak": 0.85, "decline": 0.2}
        order = {"seed": "peak", "peak": "decline", "decline": "end"}
        def critic(c):
            return Critique(qmap.get(c, 0.05), "q")
        gen = lambda c, cr, i: order.get(c, c + "!")  # noqa: E731
        result = loop.refine("seed", critic, gen, RefinementConfig(quality_threshold=0.99, max_iterations=5, patience=99, require_monotonic=False))
        # best seen was 'peak' at 0.85
        assert result.final_candidate == "peak"
        assert result.final_quality == 0.85

    def test_absolute_best_kept_even_when_below_min_delta(self):
        # D5: a candidate that is better in absolute terms but by LESS than
        # min_delta must still be returned as the best candidate.
        loop = SelfRefinementLoop()
        qmap = {"s": 0.800, "b": 0.805, "c": 0.804}
        order = {"s": "b", "b": "c"}
        def critic(c):
            return Critique(qmap.get(c, 0.05), "q")
        gen = lambda c, cr, i: order.get(c, c + "!")  # noqa: E731
        result = loop.refine(
            "s", critic, gen,
            RefinementConfig(quality_threshold=0.99, max_iterations=4, patience=2,
                             min_delta=0.01, require_monotonic=False),
        )
        # 'b' (0.805) is the absolute best seen; must be returned even though
        # 0.805 - 0.800 < min_delta (0.01).
        assert result.final_candidate == "b"
        assert abs(result.final_quality - 0.805) < 1e-9


class TestOscillationWindow:
    def test_repeat_outside_window_is_not_oscillation(self):
        # D6 decisive: candidate cycles A->B->C->D->A. With window=2, by the time
        # 'A' recurs the window only holds the last 2 hashes (D,A-being-added),
        # so 'A' is NOT in the window and must NOT be flagged as oscillation.
        # The loop instead proceeds until the iteration budget (MAX_ITERATIONS).
        loop = SelfRefinementLoop()
        cycle = {"A": "B", "B": "C", "C": "D", "D": "A"}
        result = loop.refine(
            "A", lambda c: Critique(0.3, "flat"), lambda c, cr, i: cycle[c],
            RefinementConfig(quality_threshold=0.99, patience=99, max_iterations=6,
                             oscillation_window=2, require_monotonic=False),
        )
        assert result.stop_reason == RefinementStopReason.MAX_ITERATIONS

    def test_repeat_within_window_is_oscillation(self):
        # A -> B -> A within the window is still flagged.
        loop = SelfRefinementLoop()
        seq = {"A": "B", "B": "A"}
        result = loop.refine(
            "A", lambda c: Critique(0.3, "flat"), lambda c, cr, i: seq[c],
            RefinementConfig(quality_threshold=0.99, patience=99,
                             oscillation_window=4, require_monotonic=False),
        )
        assert result.stop_reason == RefinementStopReason.OSCILLATION_DETECTED


class TestNoDoubleCritic:
    def test_critic_called_once_per_candidate(self):
        loop = SelfRefinementLoop()
        calls = {}
        def critic(c):
            calls[c] = calls.get(c, 0) + 1
            return Critique(min(1.0, len(c) / 20.0), "q")
        gen = lambda c, cr, i: c + "ab"  # noqa: E731
        loop.refine("xx", critic, gen, RefinementConfig(quality_threshold=0.95, max_iterations=10, require_monotonic=True))
        # With require_monotonic the proposed next is pre-critiqued; that critique
        # must be reused (cached) on the next loop, not recomputed.
        assert all(v == 1 for v in calls.values()), f"double critic: {calls}"


class TestValidation:
    def test_max_iterations_must_be_positive(self):
        loop = SelfRefinementLoop()
        with pytest.raises(ValidationError):
            loop.refine("x", lambda c: Critique(0.5, ""), lambda c, cr, i: c + "y", RefinementConfig(max_iterations=0))

    def test_non_string_initial_candidate_raises(self):
        loop = SelfRefinementLoop()
        with pytest.raises(ValidationError):
            loop.refine(123, lambda c: Critique(0.5, ""), lambda c, cr, i: "y")  # type: ignore[arg-type]

    def test_critic_quality_out_of_range_raises(self):
        loop = SelfRefinementLoop()
        with pytest.raises(ValidationError):
            loop.refine("x", lambda c: Critique(1.5, "bad"), lambda c, cr, i: c + "y")

    def test_generator_non_string_raises(self):
        loop = SelfRefinementLoop()
        with pytest.raises(ValidationError):
            loop.refine("x", lambda c: Critique(0.5, ""), lambda c, cr, i: 99, RefinementConfig(quality_threshold=0.99))  # type: ignore[return-value]

    def test_critic_exception_propagates(self):
        loop = SelfRefinementLoop()
        def critic(c):
            raise RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            loop.refine("x", critic, lambda c, cr, i: c + "y")

    def test_generator_exception_propagates(self):
        loop = SelfRefinementLoop()
        def gen(c, cr, i):
            raise RuntimeError("gen-boom")
        with pytest.raises(RuntimeError, match="gen-boom"):
            loop.refine("x", lambda c: Critique(0.5, ""), gen, RefinementConfig(quality_threshold=0.99))


class TestIterationRecord:
    def test_iterations_have_hashes_and_critiques(self):
        loop = SelfRefinementLoop()
        critic = critic_len(scale=8.0)
        gen = lambda c, cr, i: c + "ab"  # noqa: E731
        result = loop.refine("x", critic, gen, RefinementConfig(quality_threshold=0.9, max_iterations=5))
        assert len(result.iterations) >= 1
        for it in result.iterations:
            assert it.candidate_hash
            assert isinstance(it.critique, Critique)
            assert it.iteration >= 0
