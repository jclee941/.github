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

import pytest

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


# --- Parallel recursive descent (S1 determinism, S2 concurrency, S4 validation) ---

import threading  # noqa: E402

from scripts.evolution.errors import ValidationError  # noqa: E402


def _snapshot(node):
    """Structural snapshot used to assert parallel == sequential, byte-identical."""
    return (
        node.path,
        node.depth,
        node.initial_candidate,
        node.final_candidate,
        node.refinement.stop_reason,
        round(node.refinement.final_quality, 9),
        round(node.aggregate_quality, 9),
        node.max_depth_reached,
        tuple(_snapshot(c) for c in node.children),
    )


# Deterministic callables reused by parallel tests: a 2-level decomposable doc.
_REQ = ("intro", "usage")


def _pcritic(c: str) -> Critique:
    have = sum(1 for k in _REQ if k in c.lower())
    return Critique(have / len(_REQ), f"{have}/{len(_REQ)}")


def _pgen(c: str, cr: Critique, i: int) -> str:
    for k in _REQ:
        if k not in c.lower():
            return c + "\n" + k
    return c


def _pdecompose(c: str):
    # Root '# ' doc splits into sections; each section further splits once on '## '.
    import re as _re
    parts = []
    for block in _re.split(r"(?m)^(?=#{1,2} )", c):
        block = block.strip("\n")
        if block and block.startswith("#"):
            parts.append(RefinementPart(value=block, key=block.splitlines()[0]))
    return parts


def _precompose(original: str, refined):
    return "\n\n".join(rp.node.final_candidate for rp in refined) if refined else original


_PARALLEL_DOC = (
    "# A\n\n## A1\nx\n\n## A2\ny\n\n# B\n\n## B1\nz\n\n## B2\nw"
)


class TestParallelRecursiveRefinement:
    def _run(self, workers: int):
        refiner: RecursiveRefiner[str] = RecursiveRefiner(max_workers=workers)
        return refiner.refine_recursive(
            _PARALLEL_DOC, _pcritic, _pgen, _pdecompose, _precompose,
            RefinementConfig(quality_threshold=1.0, max_iterations=4),
            max_depth=2,
        )

    def test_parallel_equals_sequential(self):
        seq = self._run(1)
        par = self._run(8)
        assert _snapshot(par.tree) == _snapshot(seq.tree), "parallel tree != sequential tree"
        assert par.final_candidate == seq.final_candidate
        assert par.total_iterations == seq.total_iterations
        assert par.max_observed_depth == seq.max_observed_depth
        assert round(par.final_quality, 9) == round(seq.final_quality, 9)
        # the tree actually has siblings to parallelize
        assert len(seq.tree.children) >= 2

    def test_siblings_run_concurrently_when_parallel(self):
        # A child-only barrier: N sibling leaves must all enter the critic
        # simultaneously, which is only possible if they run on >1 thread.
        n = 3
        barrier = threading.Barrier(n, timeout=10)
        lock = threading.Lock()
        threads: set[int] = set()

        def critic(c: str) -> Critique:
            if c.startswith("leaf-"):
                with lock:
                    threads.add(threading.get_ident())
                barrier.wait()  # deadlocks/raises BrokenBarrier if run serially
            return Critique(1.0, "done")

        def gen(c: str, cr: Critique, i: int) -> str:
            return c

        def decompose(c: str):
            if c == "root":
                return [RefinementPart(value=f"leaf-{i}", key=str(i)) for i in range(n)]
            return []

        def recompose(o: str, refined):
            return o

        refiner: RecursiveRefiner[str] = RecursiveRefiner(max_workers=n)
        res = refiner.refine_recursive(
            "root", critic, gen, decompose, recompose,
            RefinementConfig(quality_threshold=1.0, max_iterations=2),
            max_depth=1,
        )
        assert len(res.tree.children) == n
        assert len(threads) > 1, f"expected >1 worker thread, saw {len(threads)}"

    def test_sequential_uses_single_thread(self):
        n = 3
        lock = threading.Lock()
        threads: set[int] = set()

        def critic(c: str) -> Critique:
            if c.startswith("leaf-"):
                with lock:
                    threads.add(threading.get_ident())
            return Critique(1.0, "done")

        def gen(c: str, cr: Critique, i: int) -> str:
            return c

        def decompose(c: str):
            if c == "root":
                return [RefinementPart(value=f"leaf-{i}", key=str(i)) for i in range(n)]
            return []

        refiner: RecursiveRefiner[str] = RecursiveRefiner(max_workers=1)
        refiner.refine_recursive(
            "root", critic, gen, decompose, lambda o, r: o,
            RefinementConfig(quality_threshold=1.0, max_iterations=2),
            max_depth=1,
        )
        assert len(threads) == 1, f"sequential must use one thread, saw {len(threads)}"

    def test_invalid_max_workers_raises(self):
        with pytest.raises(ValidationError):
            RecursiveRefiner(max_workers=0)
        with pytest.raises(ValidationError):
            RecursiveRefiner(max_workers=-1)

    def test_total_thread_count_is_globally_bounded(self):
        # max_workers must be a GLOBAL cap, not per-node. A wide+deep tree
        # (fanout^depth nodes) must NOT spawn threads proportional to the tree
        # size: total distinct worker threads ever used must stay <= max_workers.
        max_workers = 3
        lock = threading.Lock()
        all_threads: set[int] = set()

        def critic(c: str) -> Critique:
            with lock:
                all_threads.add(threading.get_ident())
            return Critique(1.0, "ok")

        def gen(c: str, cr: Critique, i: int) -> str:
            return c

        # Each non-leaf node decomposes into 3 children, up to max_depth=3 ->
        # 1 + 3 + 9 + 27 = 40 nodes, far more than max_workers.
        def decompose(c: str):
            if c.count(".") < 3:  # depth marker via dots
                return [RefinementPart(value=f"{c}.{i}", key=str(i)) for i in range(3)]
            return []

        refiner: RecursiveRefiner[str] = RecursiveRefiner(max_workers=max_workers)
        res = refiner.refine_recursive(
            "r", critic, gen, decompose, lambda o, r: o,
            RefinementConfig(quality_threshold=1.0, max_iterations=1),
            max_depth=3,
        )
        # the tree really is large (proves the scenario exercises depth*fanout)
        def _count(n):
            return 1 + sum(_count(c) for c in n.children)
        assert _count(res.tree) >= 40
        # GLOBAL bound: the main thread + at most (max_workers-1) helpers.
        assert len(all_threads) <= max_workers, (
            f"thread explosion: {len(all_threads)} threads used for a "
            f"{_count(res.tree)}-node tree with max_workers={max_workers}"
        )

    def test_permit_not_leaked_when_submit_raises(self, monkeypatch):
        # If executor.submit raises AFTER permits.acquire() succeeds, the permit
        # MUST be released. We instrument the semaphore to count acquire/release
        # and force submit to raise, then assert balance (acquired == released).
        import concurrent.futures as cf
        import threading as _t

        counter = {"acq": 0, "rel": 0}
        real_sema = _t.BoundedSemaphore

        class CountingSema:
            def __init__(self, n):
                self._s = real_sema(n)

            def acquire(self, blocking=True, timeout=None):
                ok = self._s.acquire(blocking=blocking, timeout=timeout)
                if ok:
                    counter["acq"] += 1
                return ok

            def release(self):
                counter["rel"] += 1
                return self._s.release()

        monkeypatch.setattr(_t, "BoundedSemaphore", CountingSema)

        def boom_submit(self, fn, *a, **k):
            raise RuntimeError("submit boom")

        monkeypatch.setattr(cf.ThreadPoolExecutor, "submit", boom_submit)

        def decompose(c: str):
            if c == "root":
                return [RefinementPart(value=f"leaf-{i}", key=str(i)) for i in range(3)]
            return []

        refiner: RecursiveRefiner[str] = RecursiveRefiner(max_workers=3)
        with pytest.raises(RuntimeError, match="submit boom"):
            refiner.refine_recursive(
                "root", lambda c: Critique(1.0, "ok"), lambda c, cr, i: c,
                decompose, lambda o, r: o,
                RefinementConfig(quality_threshold=1.0, max_iterations=1),
                max_depth=1,
            )
        # Every acquired permit must have been released despite the submit failure.
        assert counter["acq"] == counter["rel"], (
            f"permit leak: acquired={counter['acq']} released={counter['rel']}"
        )

