"""Generic-candidate tests for scripts/evolution/refinement.py (G1).

Proves the self-refinement loop flows an arbitrary candidate type ``T`` end to
end (not just ``str``): the critic receives ``T``, the generator returns ``T``,
and the result/iteration candidates are ``T`` instances. Hashing for
duplicate/oscillation detection goes through an injected serializer.
"""

from __future__ import annotations

from dataclasses import dataclass

from scripts.evolution.models import (
    Critique,
    RefinementConfig,
    RefinementPart,
    RefinementStopReason,
)
from scripts.evolution.refinement import RecursiveRefiner, SelfRefinementLoop


@dataclass(frozen=True, slots=True)
class ScoreCard:
    title: str
    score: int


def _serialize(card: ScoreCard) -> str:
    return f"{card.title}:{card.score}"


class TestGenericCandidate:
    def test_scorecard_flows_end_to_end(self):
        # quality grows with score; generator bumps the score by 1 each round.
        def critic(card: ScoreCard) -> Critique:
            return Critique(quality=min(1.0, card.score / 5.0), message=f"score={card.score}")

        def generator(card: ScoreCard, critique: Critique, iteration: int) -> ScoreCard:
            return ScoreCard(card.title, card.score + 1)

        loop: SelfRefinementLoop[ScoreCard] = SelfRefinementLoop(serializer=_serialize)
        result = loop.refine(
            ScoreCard("doc", 1),
            critic,
            generator,
            RefinementConfig(quality_threshold=0.9, max_iterations=10),
        )

        assert result.stop_reason == RefinementStopReason.THRESHOLD_REACHED
        # candidates must be ScoreCard instances, not serialized strings
        assert isinstance(result.initial_candidate, ScoreCard)
        assert isinstance(result.final_candidate, ScoreCard)
        assert result.final_candidate.score >= 5
        for it in result.iterations:
            assert isinstance(it.candidate, ScoreCard)
            assert it.candidate_hash  # serializer-derived hash present

    def test_serializer_drives_duplicate_detection(self):
        # Generator always returns the same logical card -> serializer makes the
        # hash identical -> GENERATOR_STALLED, proving the serializer (not repr)
        # is what dedupe uses.
        def critic(card: ScoreCard) -> Critique:
            return Critique(quality=0.3, message="flat")

        def generator(card: ScoreCard, critique: Critique, iteration: int) -> ScoreCard:
            return ScoreCard(card.title, card.score)  # new object, same content

        loop: SelfRefinementLoop[ScoreCard] = SelfRefinementLoop(serializer=_serialize)
        result = loop.refine(
            ScoreCard("doc", 2),
            critic,
            generator,
            RefinementConfig(quality_threshold=0.99),
        )
        assert result.stop_reason == RefinementStopReason.GENERATOR_STALLED

    def test_default_loop_still_handles_str(self):
        # No serializer -> str default must keep working identically.
        loop: SelfRefinementLoop[str] = SelfRefinementLoop()
        result = loop.refine(
            "ab",
            lambda c: Critique(min(1.0, len(c) / 6.0), "q"),
            lambda c, cr, i: c + "cd",
            RefinementConfig(quality_threshold=0.9, max_iterations=10),
        )
        assert result.final_quality >= 0.9
        assert isinstance(result.final_candidate, str)


class TestGenericRecursive:
    def test_recursive_descent_flows_nonstr_candidate(self):
        # Recursive descent must work on a non-str candidate T end-to-end:
        # decompose into ScoreCard parts, recurse, recompose, all staying typed.
        def critic(card: ScoreCard) -> Critique:
            return Critique(quality=min(1.0, card.score / 3.0), message=f"s={card.score}")

        def generator(card: ScoreCard, critique: Critique, iteration: int) -> ScoreCard:
            return ScoreCard(card.title, card.score + 1)

        def decompose(card: ScoreCard):
            # Split the root card (by title) into two children exactly once.
            # The flat refine runs BEFORE decompose, so we key off the title,
            # not the (mutated) score. Children have distinct titles -> no
            # further split.
            if card.title == "root":
                return [
                    RefinementPart(value=ScoreCard("root.a", 0), key="a"),
                    RefinementPart(value=ScoreCard("root.b", 0), key="b"),
                ]
            return []

        def recompose(original: ScoreCard, refined) -> ScoreCard:
            total = sum(rp.node.final_candidate.score for rp in refined)
            return ScoreCard(original.title, total)

        refiner: RecursiveRefiner[ScoreCard] = RecursiveRefiner(serializer=_serialize)
        result = refiner.refine_recursive(
            ScoreCard("root", 0),
            critic,
            generator,
            decompose,
            recompose,
            RefinementConfig(quality_threshold=1.0, max_iterations=5),
            max_depth=1,
        )
        assert isinstance(result.final_candidate, ScoreCard)
        assert len(result.tree.children) == 2
        for child in result.tree.children:
            assert isinstance(child.final_candidate, ScoreCard)
            assert child.max_depth_reached is True  # depth 1 == max_depth

        def _walk(node):
            yield node
            for c in node.children:
                yield from _walk(c)
        assert all(isinstance(n.final_candidate, ScoreCard) for n in _walk(result.tree))
        assert result.max_observed_depth == 1
