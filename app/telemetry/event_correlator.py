"""
Deterministic Event Correlation Engine.
Groups and correlates related pipeline failures using:
1. Repository
2. Commit identifier
3. Workflow name
4. Time window
5. Normalized failure signature (error pattern)

Provides explainable root-cause grouping without unneeded deep learning.
"""

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class FailureEvent:
    event_id: str
    repository: str
    commit_hash: str
    workflow_name: str
    error_message: str
    timestamp: datetime
    test_identifier: str | None = None


@dataclass
class CorrelatedEventGroup:
    group_id: str
    failure_signature: str
    repository: str
    workflow_name: str
    occurrence_count: int
    affected_commits: list[str]
    affected_tests: list[str]
    first_seen: str
    last_seen: str
    is_systemic: bool
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventCorrelator:
    """
    Deterministic failure clustering and event correlation engine.
    """

    def __init__(self, time_window_seconds: int = 3600):
        self.time_window = timedelta(seconds=time_window_seconds)

    @staticmethod
    def _normalize_ts(dt: datetime) -> datetime:
        """Normalizes datetime to UTC timezone-aware."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    @staticmethod
    def normalize_failure_signature(error_msg: str) -> str:
        """
        Extracts a clean, normalized failure signature by stripping variable noise
        such as memory addresses (0x7f...), line numbers, and file paths.
        """
        if not error_msg:
            return "UnknownFailure"

        msg = error_msg.strip()

        # Extract standard Python exception header if present (e.g. AssertionError, KeyError)
        match = re.search(r"([A-Za-z0-9_]+Error|[A-Za-z0-9_]+Exception):\s*(.*)", msg)
        if match:
            exc_type = match.group(1)
            exc_detail = match.group(2).strip()
            # Redact memory hex addresses
            exc_detail = re.sub(r"0x[0-9a-fA-F]+", "0x...", exc_detail)
            # Redact absolute file paths
            exc_detail = re.sub(r'["\']?[A-Za-z]:\\[^"\']+["\']?', "[PATH]", exc_detail)
            exc_detail = re.sub(r'["\']?/[^"\']+["\']?', "[PATH]", exc_detail)
            # Limit length for signature stability
            return f"{exc_type}: {exc_detail[:80]}"

        # If pytest failure summary
        if "FAILED" in msg:
            first_line = msg.splitlines()[0]
            clean = re.sub(r"0x[0-9a-fA-F]+", "0x...", first_line)
            return clean[:100]

        # Generic cleaned error line
        first_line = msg.splitlines()[0] if msg else "GenericPipelineFailure"
        return first_line[:80].strip()

    def correlate_events(self, events: list[FailureEvent]) -> list[CorrelatedEventGroup]:
        """
        Groups events by (repository, failure_signature) strictly within the configured time window.

        Enforces:
        1. Timezone-normalized chronological ordering (handles aware & naive UTC).
        2. Events separated by more than self.time_window form distinct incident groups.
        3. Repository isolation: identical errors across different repositories are never conflated.
        """
        if not events:
            return []

        # Sort chronologically by normalized timestamp (handles out-of-order events)
        sorted_events = sorted(events, key=lambda e: self._normalize_ts(e.timestamp))
        groups: list[CorrelatedEventGroup] = []

        # Map by key: (repository, signature)
        clusters: dict[str, list[FailureEvent]] = {}

        for evt in sorted_events:
            sig = self.normalize_failure_signature(evt.error_message)
            key = f"{evt.repository}::{sig}"
            if key not in clusters:
                clusters[key] = []
            clusters[key].append(evt)

        # Build correlated groups enforcing configured time window
        for key, cluster in clusters.items():
            repo, sig = key.split("::", 1)

            window_subclusters: list[list[FailureEvent]] = []
            current_subcluster: list[FailureEvent] = []

            for evt in cluster:
                evt_ts = self._normalize_ts(evt.timestamp)
                if not current_subcluster:
                    current_subcluster.append(evt)
                else:
                    first_ts = self._normalize_ts(current_subcluster[0].timestamp)
                    if (evt_ts - first_ts) <= self.time_window:
                        current_subcluster.append(evt)
                    else:
                        window_subclusters.append(current_subcluster)
                        current_subcluster = [evt]

            if current_subcluster:
                window_subclusters.append(current_subcluster)

            for sub_cluster in window_subclusters:
                commits = sorted({e.commit_hash for e in sub_cluster})
                tests = sorted({e.test_identifier for e in sub_cluster if e.test_identifier})
                workflows = sorted({e.workflow_name for e in sub_cluster})

                first_seen_dt = self._normalize_ts(sub_cluster[0].timestamp)
                last_seen_dt = self._normalize_ts(sub_cluster[-1].timestamp)

                # Deterministic group hash
                raw_hash = f"{repo}_{sig}_{first_seen_dt.isoformat()}"
                group_id = hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()[:12]

                # Systemic if multiple commits or multiple workflows experienced the exact same error
                is_systemic = len(commits) > 1 or len(workflows) > 1

                desc = (
                    f"Systemic failure: '{sig}' observed {len(sub_cluster)} times across {len(commits)} commits."
                    if is_systemic
                    else f"Isolated failure: '{sig}' observed {len(sub_cluster)} time(s) in commit {commits[0][:8]}."
                )

                groups.append(
                    CorrelatedEventGroup(
                        group_id=group_id,
                        failure_signature=sig,
                        repository=repo,
                        workflow_name=", ".join(workflows),
                        occurrence_count=len(sub_cluster),
                        affected_commits=commits,
                        affected_tests=tests,
                        first_seen=first_seen_dt.isoformat(),
                        last_seen=last_seen_dt.isoformat(),
                        is_systemic=is_systemic,
                        description=desc,
                    )
                )

        return groups
