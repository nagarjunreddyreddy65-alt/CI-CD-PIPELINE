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

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
import re
import hashlib


@dataclass
class FailureEvent:
    event_id: str
    repository: str
    commit_hash: str
    workflow_name: str
    error_message: str
    timestamp: datetime
    test_identifier: Optional[str] = None


@dataclass
class CorrelatedEventGroup:
    group_id: str
    failure_signature: str
    repository: str
    workflow_name: str
    occurrence_count: int
    affected_commits: List[str]
    affected_tests: List[str]
    first_seen: str
    last_seen: str
    is_systemic: bool
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EventCorrelator:
    """
    Deterministic failure clustering and event correlation engine.
    """

    def __init__(self, time_window_seconds: int = 3600):
        self.time_window = timedelta(seconds=time_window_seconds)

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

    def correlate_events(self, events: List[FailureEvent]) -> List[CorrelatedEventGroup]:
        """
        Groups events by (repository, failure_signature) within the sliding time window.
        """
        if not events:
            return []

        # Sort chronologically
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        groups: List[CorrelatedEventGroup] = []

        # Map by key: (repository, signature)
        clusters: Dict[str, List[FailureEvent]] = {}

        for evt in sorted_events:
            sig = self.normalize_failure_signature(evt.error_message)
            key = f"{evt.repository}::{sig}"
            if key not in clusters:
                clusters[key] = []
            clusters[key].append(evt)

        # Build correlated groups
        for key, cluster in clusters.items():
            repo, sig = key.split("::", 1)
            commits = sorted(list({e.commit_hash for e in cluster}))
            tests = sorted(list({e.test_identifier for e in cluster if e.test_identifier}))
            workflows = sorted(list({e.workflow_name for e in cluster}))

            first_seen_dt = cluster[0].timestamp
            last_seen_dt = cluster[-1].timestamp

            # Deterministic group hash
            raw_hash = f"{repo}_{sig}_{first_seen_dt.isoformat()}"
            group_id = hashlib.md5(raw_hash.encode("utf-8")).hexdigest()[:12]

            # Systemic if multiple commits or multiple workflows experienced the exact same error
            is_systemic = len(commits) > 1 or len(workflows) > 1

            desc = (
                f"Systemic failure: '{sig}' observed {len(cluster)} times across {len(commits)} commits."
                if is_systemic else
                f"Isolated failure: '{sig}' observed {len(cluster)} time(s) in commit {commits[0][:8]}."
            )

            groups.append(CorrelatedEventGroup(
                group_id=group_id,
                failure_signature=sig,
                repository=repo,
                workflow_name=", ".join(workflows),
                occurrence_count=len(cluster),
                affected_commits=commits,
                affected_tests=tests,
                first_seen=first_seen_dt.isoformat(),
                last_seen=last_seen_dt.isoformat(),
                is_systemic=is_systemic,
                description=desc,
            ))

        return groups
