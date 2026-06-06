"""Recursive regression detection across a repository's PR history.

A *regression* is specifically a finding that was previously **closed** and then
reappears in a later PR. Findings that simply remain open across PRs are
unresolved carryover, not regressions.
"""

from __future__ import annotations

from collections.abc import Sequence

from scripts.evolution.errors import FingerprintCollisionError
from scripts.evolution.fingerprint import finding_identity
from scripts.evolution.models import (
    FindingEventType,
    FindingStatus,
    PullRequestContext,
    RegressionMatch,
    ReviewFinding,
)
from scripts.evolution.storage import EvolutionStore


class RegressionDetector:
    def __init__(self, store: EvolutionStore) -> None:
        self.store = store

    def ingest_findings(
        self,
        ctx: PullRequestContext,
        findings: Sequence[ReviewFinding],
    ) -> list[RegressionMatch]:
        """Persist current findings and flag regressions.

        Each finding in ``findings`` yields exactly one ``RegressionMatch`` in
        input order. Identical findings appearing twice in the same input do not
        create duplicate rows (the second is treated as carryover), but both are
        reported.
        """
        matches: list[RegressionMatch] = []
        seen_in_batch: set[str] = set()

        for finding in findings:
            identity = finding_identity(ctx.repo, finding)
            existing = self.store.get_finding_by_fingerprint(ctx.repo, identity.fingerprint)

            if existing is not None and existing["fingerprint_full"] != identity.fingerprint_full:
                raise FingerprintCollisionError(ctx.repo, identity.fingerprint)

            if existing is None:
                self.store.upsert_finding_seen(ctx, finding, identity)
                seen_in_batch.add(identity.fingerprint)
                matches.append(
                    RegressionMatch(
                        finding=finding,
                        fingerprint=identity.fingerprint,
                        previous_status=FindingStatus.OPEN,
                        first_pr_url=ctx.pr_url,
                        first_pr_number=ctx.pr_number,
                        closed_at=None,
                        is_regression=False,
                        reason="new finding",
                    )
                )
                continue

            previous_status = FindingStatus(existing["status"])
            finding_id = int(existing["id"])

            if previous_status == FindingStatus.CLOSED:
                self.store.reopen_finding_with_event(
                    finding_id,
                    ctx,
                    finding,
                    FindingEventType.REGRESSED,
                    {
                        "closed_at": existing["closed_at"],
                        "first_pr_url": existing["first_pr_url"],
                        "first_pr_number": existing["first_pr_number"],
                    },
                )
                matches.append(
                    RegressionMatch(
                        finding=finding,
                        fingerprint=identity.fingerprint,
                        previous_status=FindingStatus.CLOSED,
                        first_pr_url=existing["first_pr_url"],
                        first_pr_number=existing["first_pr_number"],
                        closed_at=existing["closed_at"],
                        is_regression=True,
                        reason="previously closed finding reappeared (regression)",
                    )
                )
                continue

            # open or ignored carryover: count it once per batch only
            if identity.fingerprint not in seen_in_batch:
                self.store.upsert_finding_seen(ctx, finding, identity)
                seen_in_batch.add(identity.fingerprint)
            matches.append(
                RegressionMatch(
                    finding=finding,
                    fingerprint=identity.fingerprint,
                    previous_status=previous_status,
                    first_pr_url=existing["first_pr_url"],
                    first_pr_number=existing["first_pr_number"],
                    closed_at=existing["closed_at"],
                    is_regression=False,
                    reason=f"existing {previous_status} finding (carryover)",
                )
            )

        return matches

    def mark_closed(
        self,
        repo: str,
        fingerprint: str,
        *,
        reason: str = "resolved",
        ctx: PullRequestContext | None = None,
    ) -> bool:
        """Mark a finding closed (e.g. when its PR/issue is resolved)."""
        return self.store.close_finding(repo, fingerprint, reason=reason, ctx=ctx)

    def ignore(
        self,
        repo: str,
        fingerprint: str,
        *,
        reason: str = "ignored",
        ctx: PullRequestContext | None = None,
    ) -> bool:
        """Mark a finding as ignored (false positive). Reappearance is not a regression."""
        existing = self.store.get_finding_by_fingerprint(repo, fingerprint)
        if existing is None:
            return False
        with self.store.transaction() as conn:
            conn.execute(
                "UPDATE findings SET status = 'ignored' WHERE repo = ? AND fingerprint = ?",
                (repo, fingerprint),
            )
        self.store.record_finding_event(
            int(existing["id"]), ctx or PullRequestContext(repo), FindingEventType.IGNORED, {"reason": reason}
        )
        return True
