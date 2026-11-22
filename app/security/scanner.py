"""
Security Scanning Integration & Parsers.
Integrates Bandit (SAST), pip-audit (SCA), and Gitleaks (Secret Detection).

Security Policy:
1. High and Critical severity findings MUST block pipeline release.
2. Secrets, tokens, and passwords MUST be redacted before logging or persistence.
3. Every finding records tool name, severity, summary, and location.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from app.core.logging import redact_secrets


class SecuritySeverity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ScanStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"


# Numerical mapping for severity comparisons
SEVERITY_ORDER: dict[SecuritySeverity, int] = {
    SecuritySeverity.NONE: 0,
    SecuritySeverity.LOW: 1,
    SecuritySeverity.MEDIUM: 2,
    SecuritySeverity.HIGH: 3,
    SecuritySeverity.CRITICAL: 4,
}


@dataclass
class SecurityFinding:
    tool_name: str
    severity: SecuritySeverity
    rule_id: str
    title: str
    description: str
    file_path: str | None = None
    line_number: int | None = None
    redacted_snippet: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


@dataclass
class ScanResult:
    tool_name: str
    status: ScanStatus
    highest_severity: SecuritySeverity
    findings_count: int
    findings: list[SecurityFinding]
    summary: str
    should_block_release: bool
    executed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status.value,
            "highest_severity": self.highest_severity.value,
            "findings_count": self.findings_count,
            "findings": [f.to_dict() for f in self.findings],
            "summary": self.summary,
            "should_block_release": self.should_block_release,
            "executed_at": self.executed_at,
        }


class BanditParser:
    """Parses Bandit SAST JSON output."""

    @staticmethod
    def parse(raw_json: Any) -> ScanResult:
        if isinstance(raw_json, str):
            try:
                data = json.loads(raw_json)
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                return ScanResult(
                    tool_name="Bandit",
                    status=ScanStatus.FAILED,
                    highest_severity=SecuritySeverity.HIGH,
                    findings_count=0,
                    findings=[],
                    summary=f"Invalid Bandit JSON: {e}",
                    should_block_release=True,
                )
        else:
            data = raw_json or {}

        results = data.get("results", [])
        findings: list[SecurityFinding] = []
        highest_sev = SecuritySeverity.NONE

        for item in results:
            raw_sev = str(item.get("issue_severity", "LOW")).upper()
            try:
                sev = SecuritySeverity(raw_sev)
            except ValueError:
                sev = SecuritySeverity.MEDIUM

            if SEVERITY_ORDER[sev] > SEVERITY_ORDER[highest_sev]:
                highest_sev = sev

            snippet = item.get("code")
            redacted_code = redact_secrets(snippet) if snippet else None

            findings.append(
                SecurityFinding(
                    tool_name="Bandit",
                    severity=sev,
                    rule_id=str(item.get("test_id", "B000")),
                    title=str(item.get("issue_text", "Static analysis security issue")),
                    description=f"{item.get('test_name', '')}: {item.get('issue_text', '')}",
                    file_path=item.get("filename"),
                    line_number=item.get("line_number"),
                    redacted_snippet=redacted_code,
                )
            )

        should_block = SEVERITY_ORDER[highest_sev] >= SEVERITY_ORDER[SecuritySeverity.HIGH]
        status = ScanStatus.PASSED
        if should_block:
            status = ScanStatus.FAILED
        elif len(findings) > 0:
            status = ScanStatus.WARNING

        summary = (
            f"Bandit scan identified {len(findings)} issues. Highest severity: {highest_sev.value}."
        )
        return ScanResult(
            tool_name="Bandit",
            status=status,
            highest_severity=highest_sev,
            findings_count=len(findings),
            findings=findings,
            summary=summary,
            should_block_release=should_block,
        )


class PipAuditParser:
    """Parses pip-audit Dependency Vulnerability JSON output."""

    @staticmethod
    def parse(raw_json: Any) -> ScanResult:
        if isinstance(raw_json, str):
            try:
                data = json.loads(raw_json)
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                return ScanResult(
                    tool_name="pip-audit",
                    status=ScanStatus.FAILED,
                    highest_severity=SecuritySeverity.HIGH,
                    findings_count=0,
                    findings=[],
                    summary=f"Invalid pip-audit JSON: {e}",
                    should_block_release=True,
                )
        else:
            data = raw_json or {}

        # pip-audit outputs a list of dependencies or a dict with "dependencies"
        dependencies = data if isinstance(data, list) else data.get("dependencies", [])
        findings: list[SecurityFinding] = []
        highest_sev = SecuritySeverity.NONE

        for dep in dependencies:
            name = dep.get("name", "unknown")
            version = dep.get("version", "unknown")
            vulns = dep.get("vulns", [])

            for v in vulns:
                # Default unknown vulnerability severity to HIGH in SCA scans
                vuln_id = v.get("id", "VULN-UNKNOWN")
                desc = v.get("description", "Vulnerable package dependency")
                fix_vers = v.get("fix_versions", [])

                # In dependency audits, known CVEs default to HIGH unless specified
                sev = SecuritySeverity.HIGH
                if SEVERITY_ORDER[sev] > SEVERITY_ORDER[highest_sev]:
                    highest_sev = sev

                findings.append(
                    SecurityFinding(
                        tool_name="pip-audit",
                        severity=sev,
                        rule_id=vuln_id,
                        title=f"Vulnerable package: {name}=={version}",
                        description=f"{desc}. Fix available in: {', '.join(fix_vers) if fix_vers else 'None'}",
                        file_path="requirements.txt",
                        line_number=None,
                        redacted_snippet=f"{name}=={version}",
                    )
                )

        should_block = SEVERITY_ORDER[highest_sev] >= SEVERITY_ORDER[SecuritySeverity.HIGH]
        status = ScanStatus.PASSED
        if should_block:
            status = ScanStatus.FAILED
        elif len(findings) > 0:
            status = ScanStatus.WARNING

        summary = f"pip-audit found {len(findings)} vulnerable dependencies. Highest severity: {highest_sev.value}."
        return ScanResult(
            tool_name="pip-audit",
            status=status,
            highest_severity=highest_sev,
            findings_count=len(findings),
            findings=findings,
            summary=summary,
            should_block_release=should_block,
        )


class GitleaksParser:
    """Parses Gitleaks Secret Detection JSON output and sanitizes secrets."""

    @staticmethod
    def parse(raw_json: Any) -> ScanResult:
        if isinstance(raw_json, str):
            try:
                data = json.loads(raw_json)
            except (json.JSONDecodeError, TypeError, ValueError):
                data = []
        else:
            data = raw_json or []

        findings: list[SecurityFinding] = []
        highest_sev = SecuritySeverity.NONE

        for item in data:
            # Any leaked secret is CRITICAL
            sev = SecuritySeverity.CRITICAL
            highest_sev = sev

            rule_id = item.get("RuleID", "generic-secret")
            desc = item.get("Description", "Detected exposed secret/token")
            file_path = item.get("File", "unknown")
            start_line = item.get("StartLine")

            # CRITICAL PRIVACY: Never record the raw secret!
            findings.append(
                SecurityFinding(
                    tool_name="Gitleaks",
                    severity=sev,
                    rule_id=rule_id,
                    title=f"Secret leak: {desc}",
                    description=f"Secret detected in {file_path} at line {start_line}",
                    file_path=file_path,
                    line_number=start_line,
                    redacted_snippet="[REDACTED_SECRET]",
                )
            )

        should_block = len(findings) > 0
        status = ScanStatus.FAILED if should_block else ScanStatus.PASSED
        summary = f"Gitleaks identified {len(findings)} exposed secrets in repository."

        return ScanResult(
            tool_name="Gitleaks",
            status=status,
            highest_severity=highest_sev,
            findings_count=len(findings),
            findings=findings,
            summary=summary,
            should_block_release=should_block,
        )


class SecurityScanner:
    """Unified security scanner evaluator enforcing release blocking rules."""

    @classmethod
    def evaluate_scan(cls, tool_name: str, raw_output: Any) -> ScanResult:
        tool_lower = tool_name.lower().replace("-", "").replace("_", "")
        if "bandit" in tool_lower:
            return BanditParser.parse(raw_output)
        elif "pipaudit" in tool_lower or "audit" in tool_lower:
            return PipAuditParser.parse(raw_output)
        elif "gitleaks" in tool_lower or "secret" in tool_lower:
            return GitleaksParser.parse(raw_output)
        else:
            return ScanResult(
                tool_name=tool_name,
                status=ScanStatus.WARNING,
                highest_severity=SecuritySeverity.LOW,
                findings_count=0,
                findings=[],
                summary=f"Unknown security scanner tool: {tool_name}",
                should_block_release=False,
            )
