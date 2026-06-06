"""Generic, recursive self-refinement with convergence and anti-oscillation guards.

Pure and injectable, parametric over a candidate type ``T``. ``SelfRefinementLoop``
receives an initial candidate of type ``T``, a deterministic
``critic(candidate) -> Critique`` and a deterministic
``generator(candidate, last_critique, next_iteration) -> T``, plus an optional
``serializer(candidate) -> str`` used for hashing/oscillation detection (the
default serializer handles ``str`` and rejects other types without one). It
iterates critique -> regenerate until a stopping condition fires, then returns the
BEST candidate seen (not necessarily the last).

``RecursiveRefiner`` adds depth-bounded recursive descent: refine a candidate,
``decompose`` it into ordered parts, recursively refine each part (bounded by
``max_depth``), ``recompose`` the refined parts, then re-refine the recomposed
candidate so a parent reflects its improved children.

Stopping conditions (flat loop), in priority order:
  1. invalid input                         -> ValidationError
  2. duplicate candidate already seen       -> DUPLICATE_CANDIDATE / OSCILLATION_DETECTED
  3. quality >= threshold                   -> THRESHOLD_REACHED
  4. iteration budget exhausted             -> MAX_ITERATIONS
  5. no improvement for `patience` rounds   -> NO_MONOTONIC_IMPROVEMENT
  6. generator returns identical candidate  -> GENERATOR_STALLED
  7. proposed next regresses (> min_delta)  -> NO_MONOTONIC_IMPROVEMENT (monotonic guard)
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Generic, TypeVar

from scripts.evolution.errors import ValidationError
from scripts.evolution.models import (
    CandidateSerializer,
    Critic,
    Critique,
    Generator,
    PartDecomposer,
    PartRecomposer,
    QualityAggregator,
    RecursiveRefinementNode,
    RecursiveRefinementResult,
    RefinedPart,
    RefinementConfig,
    RefinementIteration,
    RefinementResult,
    RefinementStopReason,
)

# Re-declared locally (not imported) so type checkers bind Generic[T] to a
# TypeVar defined in this module's scope; runtime behavior is identical.
T = TypeVar("T")


def _normalize_candidate(value: str) -> str:
    """Normalize for oscillation/dup detection: strip + rstrip each line.

    Does NOT lowercase -- case may be meaningful in code candidates.
    """
    return "\n".join(line.rstrip() for line in value.strip().splitlines())


def default_candidate_serializer(value: object) -> str:
    """Default serializer: str candidates are normalized line-wise; any other
    candidate type must supply its own serializer (we refuse to guess a stable
    text form for arbitrary objects)."""
    if isinstance(value, str):
        return _normalize_candidate(value)
    raise ValidationError(
        "non-str candidate requires an explicit serializer on SelfRefinementLoop"
    )


def _candidate_hash(value: str) -> str:
    return hashlib.sha256(_normalize_candidate(value).encode("utf-8")).hexdigest()


def _validate_config(config: RefinementConfig) -> None:
    if config.max_iterations < 1:
        raise ValidationError("max_iterations must be >= 1")
    if not (0.0 <= config.quality_threshold <= 1.0):
        raise ValidationError("quality_threshold must be in [0, 1]")
    if not (0.0 <= config.min_delta <= 1.0):
        raise ValidationError("min_delta must be in [0, 1]")
    if config.patience < 1:
        raise ValidationError("patience must be >= 1")
    if config.oscillation_window < 2:
        raise ValidationError("oscillation_window must be >= 2")


def _validate_critique(critique: Critique) -> None:
    if not isinstance(critique, Critique):
        raise ValidationError("critic must return a Critique")
    if not (0.0 <= critique.quality <= 1.0):
        raise ValidationError("critique.quality must be in [0, 1]")


class SelfRefinementLoop(Generic[T]):
    def __init__(self, serializer: CandidateSerializer[T] | None = None) -> None:
        # Default serializer handles str; non-str candidates must inject one.
        self._serialize: CandidateSerializer[T] = serializer or default_candidate_serializer

    def _hash(self, candidate: T) -> str:
        serialized = self._serialize(candidate)
        if not isinstance(serialized, str):
            raise ValidationError("serializer must return a str")
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def refine(
        self,
        initial_candidate: T,
        critic: Critic[T],
        generator: Generator[T],
        config: RefinementConfig = RefinementConfig(),
    ) -> RefinementResult[T]:
        _validate_config(config)
        # Validate the initial candidate is serializable (this also rejects a
        # bare str when a serializer is absent only if the serializer says so).
        self._hash(initial_candidate)

        current = initial_candidate
        iterations: list[RefinementIteration[T]] = []
        # Sliding window of recently-seen candidate hashes (D6: oscillation is
        # only detected within `oscillation_window` iterations, not forever).
        recent_hashes: list[str] = []
        best_candidate = current
        best_quality = -1.0
        best_for_patience = -1.0
        no_improvement_count = 0
        pending_critique: Critique | None = None

        iteration = 0
        while True:
            # Reuse the critique computed by the monotonic look-ahead, if any.
            if pending_critique is not None:
                critique = pending_critique
                pending_critique = None
            else:
                critique = critic(current)
                _validate_critique(critique)

            current_hash = self._hash(current)

            if current_hash in recent_hashes:
                # Immediate self-repeat (generator returned what it just made) is a
                # duplicate; a repeat after intervening distinct candidates is an
                # oscillation. Both are within the sliding window.
                stop = (
                    RefinementStopReason.DUPLICATE_CANDIDATE
                    if recent_hashes and recent_hashes[-1] == current_hash
                    else RefinementStopReason.OSCILLATION_DETECTED
                )
                iterations.append(
                    RefinementIteration(iteration, current, current_hash, critique, accepted=False)
                )
                return self._result(initial_candidate, best_candidate, best_quality, stop, iterations)

            recent_hashes.append(current_hash)
            if len(recent_hashes) > config.oscillation_window:
                recent_hashes.pop(0)

            # D5: track the ABSOLUTE best candidate seen, independent of the
            # monotonic-improvement patience counter. A candidate that is better
            # in absolute terms (even by < min_delta) is still retained as best.
            if critique.quality > best_quality:
                best_candidate = current
                best_quality = critique.quality

            # Patience counter uses the min_delta improvement threshold: only a
            # meaningful improvement resets it.
            improved = critique.quality >= best_for_patience + config.min_delta
            if improved or best_for_patience < 0:
                best_for_patience = critique.quality
                no_improvement_count = 0
                accepted = True
            else:
                no_improvement_count += 1
                accepted = False

            iterations.append(
                RefinementIteration(iteration, current, current_hash, critique, accepted=accepted)
            )

            if critique.quality >= config.quality_threshold:
                return self._result(
                    initial_candidate, best_candidate, best_quality,
                    RefinementStopReason.THRESHOLD_REACHED, iterations,
                )

            if iteration >= config.max_iterations:
                return self._result(
                    initial_candidate, best_candidate, best_quality,
                    RefinementStopReason.MAX_ITERATIONS, iterations,
                )

            if no_improvement_count >= config.patience:
                return self._result(
                    initial_candidate, best_candidate, best_quality,
                    RefinementStopReason.NO_MONOTONIC_IMPROVEMENT, iterations,
                )

            next_candidate = generator(current, critique, iteration + 1)
            next_hash = self._hash(next_candidate)

            if next_hash == current_hash:
                return self._result(
                    initial_candidate, best_candidate, best_quality,
                    RefinementStopReason.GENERATOR_STALLED, iterations,
                )

            if config.require_monotonic:
                next_critique = critic(next_candidate)
                _validate_critique(next_critique)
                if next_critique.quality + config.min_delta < critique.quality:
                    return self._result(
                        initial_candidate, best_candidate, best_quality,
                        RefinementStopReason.NO_MONOTONIC_IMPROVEMENT, iterations,
                    )
                pending_critique = next_critique  # reuse next round (no double critic)

            current = next_candidate
            iteration += 1

    def _result(
        self,
        initial: T,
        best_candidate: T,
        best_quality: float,
        stop_reason: RefinementStopReason,
        iterations: list[RefinementIteration[T]],
    ) -> RefinementResult[T]:
        return RefinementResult(
            initial_candidate=initial,
            final_candidate=best_candidate,
            final_quality=max(best_quality, 0.0),
            stop_reason=stop_reason,
            iterations=tuple(iterations),
        )


def _default_quality_aggregator(
    own_quality: float, children: Sequence[RecursiveRefinementNode[T]]
) -> float:
    """Deterministic fold: arithmetic mean of this node's own refined quality and
    each child's aggregate quality. A leaf (no children) aggregates to its own
    quality."""
    values = [own_quality, *(c.aggregate_quality for c in children)]
    return sum(values) / len(values)


class RecursiveRefiner(Generic[T]):
    """Depth-bounded recursive self-refinement.

    For each candidate: (1) refine it flat with ``SelfRefinementLoop``; (2) if the
    current depth is below ``max_depth``, ``decompose`` the *refined* candidate
    into ordered parts and recurse into each; (3) ``recompose`` the refined parts
    back into a final candidate and refine that recomposed candidate once more so
    the parent reflects its improved children. Recursion is bounded solely by
    ``max_depth`` (the anti-infinite-recursion guard): a node at ``max_depth`` is
    refined but never decomposed.

    Parallelism: ``max_workers`` (default 1 = sequential, byte-identical to the
    original behavior) refines sibling subtrees concurrently. A SINGLE shared,
    bounded thread pool is created per ``refine_recursive`` call, so the total
    number of live helper threads is globally capped at ``max_workers - 1``
    regardless of tree width/depth (no thread explosion). Each sibling is
    offloaded only if a global permit is free; otherwise it runs inline in the
    current thread, which guarantees forward progress (no nested-submit
    deadlock). Children are always collected in original index order (never
    completion order), so the resulting tree is deterministic and equal to the
    sequential result. When ``max_workers > 1`` ALL injected callables (critic,
    generator, decompose, recompose, serializer, aggregator) MUST be pure /
    thread-safe, since sibling subtrees invoke them concurrently.
    """

    def __init__(
        self,
        *,
        serializer: CandidateSerializer[T] | None = None,
        quality_aggregator: QualityAggregator[T] | None = None,
        max_workers: int = 1,
    ) -> None:
        if max_workers < 1:
            raise ValidationError("max_workers must be >= 1")
        self._loop: SelfRefinementLoop[T] = SelfRefinementLoop(serializer)
        self._aggregate: QualityAggregator[T] = quality_aggregator or _default_quality_aggregator
        # >1 refines sibling subtrees concurrently (deterministic: children are
        # always collected in original index order). When >1, all injected
        # callables (critic/generator/decompose/recompose/serializer/aggregator)
        # MUST be pure / thread-safe. Default 1 = sequential, identical behavior.
        self._max_workers = max_workers

    def refine_recursive(
        self,
        initial_candidate: T,
        critic: Critic[T],
        generator: Generator[T],
        decompose: PartDecomposer[T],
        recompose: PartRecomposer[T],
        config: RefinementConfig = RefinementConfig(),
        *,
        max_depth: int = 1,
    ) -> RecursiveRefinementResult[T]:
        if max_depth < 0:
            raise ValidationError("max_depth must be >= 0")
        # A single shared, bounded pool for the ENTIRE recursion so total live
        # helper threads are globally capped at max_workers-1 (the calling thread
        # always does work too). A non-blocking permit gate (try-acquire, else run
        # inline) guarantees forward progress => no nested-submit deadlock, while
        # keeping the result tree deterministic (children stay in index order).
        if self._max_workers > 1:
            executor: ThreadPoolExecutor | None = ThreadPoolExecutor(max_workers=self._max_workers - 1)
            permits: threading.BoundedSemaphore | None = threading.BoundedSemaphore(self._max_workers - 1)
        else:
            executor = None
            permits = None
        try:
            tree = self._refine_node(
                initial_candidate, critic, generator, decompose, recompose, config,
                depth=0, max_depth=max_depth, path=(),
                executor=executor, permits=permits,
            )
        finally:
            if executor is not None:
                executor.shutdown(wait=True)
        return RecursiveRefinementResult(
            initial_candidate=initial_candidate,
            final_candidate=tree.final_candidate,
            final_quality=tree.aggregate_quality,
            tree=tree,
            total_iterations=_count_iterations(tree),
            max_observed_depth=_max_depth(tree),
        )

    def _refine_node(
        self,
        candidate: T,
        critic: Critic[T],
        generator: Generator[T],
        decompose: PartDecomposer[T],
        recompose: PartRecomposer[T],
        config: RefinementConfig,
        *,
        depth: int,
        max_depth: int,
        path: tuple[int, ...],
        executor: ThreadPoolExecutor | None = None,
        permits: "threading.BoundedSemaphore | None" = None,
    ) -> RecursiveRefinementNode[T]:
        # 1) Flat refinement of this candidate.
        flat = self._loop.refine(candidate, critic, generator, config)
        at_ceiling = depth >= max_depth

        # 2) Leaf node: at the depth ceiling we never decompose further.
        if at_ceiling:
            return RecursiveRefinementNode(
                path=path,
                depth=depth,
                initial_candidate=candidate,
                final_candidate=flat.final_candidate,
                refinement=flat,
                children=(),
                aggregate_quality=flat.final_quality,
                max_depth_reached=True,
            )

        # 3) Decompose the refined candidate and recurse into each part.
        parts = list(decompose(flat.final_candidate))
        if not parts:
            # No decomposition -> behaves exactly like a plain refine().
            return RecursiveRefinementNode(
                path=path,
                depth=depth,
                initial_candidate=candidate,
                final_candidate=flat.final_candidate,
                refinement=flat,
                children=(),
                aggregate_quality=flat.final_quality,
                max_depth_reached=False,
            )

        refined_parts: list[RefinedPart[T]] = []
        children: list[RecursiveRefinementNode[T]] = []
        if executor is None or permits is None or len(parts) <= 1:
            # Sequential: identical to the original behavior.
            for index, part in enumerate(parts):
                child = self._refine_node(
                    part.value, critic, generator, decompose, recompose, config,
                    depth=depth + 1, max_depth=max_depth, path=(*path, index),
                    executor=executor, permits=permits,
                )
                children.append(child)
                refined_parts.append(RefinedPart(part=part, node=child))
        else:
            # Parallel: offload each sibling subtree to the SHARED pool only if a
            # global permit is free (non-blocking). If the global concurrency cap
            # is already saturated, run that sibling inline in this thread. This
            # bounds total live helper threads at max_workers-1 and cannot
            # deadlock (no thread ever blocks waiting for a permit). Children are
            # still assembled in original index order, so output is deterministic.
            slots: list = []  # (part, future-or-None, inline-node-or-None), index-ordered
            for index, part in enumerate(parts):
                child_path = (*path, index)
                if permits.acquire(blocking=False):
                    def _run(p=part.value, cp=child_path) -> RecursiveRefinementNode[T]:
                        try:
                            return self._refine_node(
                                p, critic, generator, decompose, recompose, config,
                                depth=depth + 1, max_depth=max_depth, path=cp,
                                executor=executor, permits=permits,
                            )
                        finally:
                            permits.release()
                    try:
                        future = executor.submit(_run)
                    except BaseException:
                        # submit never accepted the task, so _run (and its
                        # permits.release) will never run -> release here to
                        # avoid leaking the permit for the rest of this call.
                        permits.release()
                        raise
                    slots.append((part, future, None))
                else:
                    node = self._refine_node(
                        part.value, critic, generator, decompose, recompose, config,
                        depth=depth + 1, max_depth=max_depth, path=child_path,
                        executor=executor, permits=permits,
                    )
                    slots.append((part, None, node))
            for part, future, node in slots:
                child = future.result() if future is not None else node
                children.append(child)
                refined_parts.append(RefinedPart(part=part, node=child))

        # 4) Recompose refined parts, then refine the recomposed candidate once
        #    more so the parent reflects its improved children.
        recomposed = recompose(flat.final_candidate, refined_parts)
        parent_refine = self._loop.refine(recomposed, critic, generator, config)
        child_tuple = tuple(children)
        return RecursiveRefinementNode(
            path=path,
            depth=depth,
            initial_candidate=candidate,
            final_candidate=parent_refine.final_candidate,
            refinement=parent_refine,
            pre_refinement=flat,
            children=child_tuple,
            aggregate_quality=self._aggregate(parent_refine.final_quality, child_tuple),
            max_depth_reached=False,
        )


def _count_iterations(node: RecursiveRefinementNode[T]) -> int:
    own = len(node.refinement.iterations)
    if node.pre_refinement is not None:
        own += len(node.pre_refinement.iterations)
    return own + sum(_count_iterations(c) for c in node.children)


def _max_depth(node: RecursiveRefinementNode[T]) -> int:
    return max([node.depth, *(_max_depth(c) for c in node.children)])
