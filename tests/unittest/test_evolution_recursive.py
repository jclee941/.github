"""Tests for recursive descent refinement (R1-R4).

``RecursiveRefiner`` decomposes a candidate into ordered parts, refines each
part with the (generic) ``SelfRefinementLoop``, recurses into decomposable parts
up to ``max_depth``, then recomposes the refined parts back into a candidate.

Surfaces under test:
  R1 happy path        -- multi-section doc fully refined via recursion.
  R2 depth-limit guard -- recursion stops at max_depth, no exception, leaf refined.
  R3 leaf regression   -- empty decomposition == plain SelfRefinementLoop.refine().
  R4 determinism       -- identical inputs produce identical trees.
"""

from __future__ import annotations

import re
from typing import Sequence

from scripts.evolution.models import (
    Critique,
    RecursiveRefinementNode,
    RecursiveRefinementResult,
    RefinedPart,
    RefinementConfig,
    RefinementPart,
)
from scripts.evolution.refinement import RecursiveRefiner, SelfRefinementLoop

REQUIRED = ("intro", "usage")


def _section_critic(candidate: str) -> Critique:
    # Quality = fraction of required keywords present (case-insensitive).
    have = sum(1 for kw in REQUIRED if kw in candidate.lower())
    return Critique(quality=have / len(REQUIRED), message=f"{have}/{len(REQUIRED)}")


def _section_generator(candidate: str, critique: Critique, iteration: int) -> str:
    for kw in REQUIRED:
        if kw not in candidate.lower():
            return candidate + f"\n{kw}"
    return candidate


def _split_sections(doc: str) -> Sequence[RefinementPart[str]]:
    """Decompose a markdown doc into one part per '# Heading' section."""
    parts: list[RefinementPart[str]] = []
    blocks = re.split(r"(?m)^(?=# )", doc)
    for block in blocks:
        block = block.strip("\n")
        if block:
            parts.append(RefinementPart(value=block, key=block.splitlines()[0]))
    return parts


def _join_sections(original: str, refined: Sequence[RefinedPart[str]]) -> str:
    return "\n\n".join(rp.node.final_candidate for rp in refined)


DOC = "# Intro\n\nTODO intro.\n\n# Usage\n\nTODO usage."


class TestRecursiveHappyPath:
    def test_multi_section_refined_and_recomposed(self):
        refiner: RecursiveRefiner[str] = RecursiveRefiner()
        result = refiner.refine_recursive(
            DOC,
            _section_critic,
            _section_generator,
            _split_sections,
            _join_sections,
            RefinementConfig(quality_threshold=1.0, max_iterations=5),
            max_depth=1,
        )
        assert isinstance(result, RecursiveRefinementResult)
        # root has two section children
        assert len(result.tree.children) == 2
        # every section got both required keywords (recomposed doc covers all)
        assert "intro" in result.final_candidate.lower()
        assert "usage" in result.final_candidate.lower()
        # total_iterations sums BOTH the post-recompose refinement AND the
        # pre-decompose flat refinement for every node that ran one.
        def _count(node: RecursiveRefinementNode[str]) -> int:
            own = len(node.refinement.iterations)
            if node.pre_refinement is not None:
                own += len(node.pre_refinement.iterations)
            return own + sum(_count(c) for c in node.children)
        assert result.total_iterations == _count(result.tree)
        assert result.max_observed_depth <= 1


class TestDepthGuard:
    def test_recursive_refinement_respects_max_depth(self):
        # A decompose fn that ALWAYS yields one child would recurse forever
        # without a depth guard. max_depth must stop descent while still
        # refining the leaf candidate.
        def always_one(candidate: str) -> Sequence[RefinementPart[str]]:
            return [RefinementPart(value=candidate + ".", key="child")]

        def take_first(original: str, refined: Sequence[RefinedPart[str]]) -> str:
            return refined[0].node.final_candidate if refined else original

        refiner: RecursiveRefiner[str] = RecursiveRefiner()
        result = refiner.refine_recursive(
            "intro usage",
            _section_critic,
            _section_generator,
            always_one,
            take_first,
            RefinementConfig(quality_threshold=1.0, max_iterations=3),
            max_depth=2,
        )
        assert result.max_observed_depth == 2
        # The deepest node must be marked as having hit the depth ceiling and
        # must NOT have decomposed further.
        node = result.tree
        while node.children:
            node = node.children[0]
        assert node.depth == 2
        assert node.children == ()
        assert node.max_depth_reached is True


class TestLeafRegression:
    def test_recursive_refinement_matches_plain_loop_for_leaf(self):
        # Empty decomposition -> recursive result must equal a plain refine().
        def no_parts(candidate: str) -> Sequence[RefinementPart[str]]:
            return []

        def identity(original: str, refined: Sequence[RefinedPart[str]]) -> str:
            return original

        config = RefinementConfig(quality_threshold=1.0, max_iterations=5)
        refiner: RecursiveRefiner[str] = RecursiveRefiner()
        rec = refiner.refine_recursive(
            "intro", _section_critic, _section_generator, no_parts, identity, config, max_depth=3,
        )
        plain = SelfRefinementLoop().refine("intro", _section_critic, _section_generator, config)

        assert rec.tree.children == ()
        assert rec.final_candidate == plain.final_candidate
        assert rec.final_quality == plain.final_quality
        assert rec.tree.refinement.stop_reason == plain.stop_reason


class TestDeterminism:
    def test_recursive_refinement_is_deterministic(self):
        refiner: RecursiveRefiner[str] = RecursiveRefiner()
        config = RefinementConfig(quality_threshold=1.0, max_iterations=5)
        r1 = refiner.refine_recursive(
            DOC, _section_critic, _section_generator, _split_sections, _join_sections, config, max_depth=1,
        )
        r2 = refiner.refine_recursive(
            DOC, _section_critic, _section_generator, _split_sections, _join_sections, config, max_depth=1,
        )

        def _snapshot(node: RecursiveRefinementNode[str]):
            return (
                node.path,
                node.depth,
                node.final_candidate,
                node.refinement.stop_reason,
                round(node.aggregate_quality, 9),
                tuple(_snapshot(c) for c in node.children),
            )

        assert _snapshot(r1.tree) == _snapshot(r2.tree)
        assert r1.final_candidate == r2.final_candidate
        assert r1.total_iterations == r2.total_iterations


class TestIterationAccounting:
    def test_total_iterations_counts_all_refine_work(self):
        # An internal node runs TWO flat refinements: one pre-decompose (to pick
        # the decomposition input) and one post-recompose. total_iterations MUST
        # account for every SelfRefinementLoop.refine() iteration actually run,
        # not just the post-recompose pass.
        from scripts.evolution.refinement import SelfRefinementLoop

        actual = {"iterations": 0}
        real_refine = SelfRefinementLoop.refine

        def spy_refine(self, initial, critic, generator, config=RefinementConfig()):
            result = real_refine(self, initial, critic, generator, config)
            actual["iterations"] += len(result.iterations)
            return result

        # One decompose pass yields a single child so the root is an internal
        # node (two flat refines) and the child is a leaf (one flat refine).
        def one_child(candidate: str):
            return [RefinementPart(value=candidate + ".child", key="c")]

        def take_first(original, refined):
            return refined[0].node.final_candidate if refined else original

        import unittest.mock as mock
        with mock.patch.object(SelfRefinementLoop, "refine", spy_refine):
            refiner: RecursiveRefiner[str] = RecursiveRefiner()
            result = refiner.refine_recursive(
                "intro usage",
                _section_critic,
                _section_generator,
                one_child,
                take_first,
                RefinementConfig(quality_threshold=1.0, max_iterations=3),
                max_depth=1,
            )
        assert result.total_iterations == actual["iterations"], (
            f"total_iterations={result.total_iterations} but refine() actually "
            f"ran {actual['iterations']} iterations"
        )
