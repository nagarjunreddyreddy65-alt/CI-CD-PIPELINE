"""
Unit Tests for Security Scanners (Bandit, pip-audit, Gitleaks).
Verifies parsing, privacy-aware secret redaction, and release blocking policy.
"""

from app.security.scanner import (
    BanditParser,
    GitleaksParser,
    PipAuditParser,
    ScanStatus,
    SecurityScanner,
    SecuritySeverity,
)


def test_bandit_parser_clean():
    raw = {"results": [], "metrics": {"_totals": {"loc": 500}}}
    result = BanditParser.parse(raw)
    assert result.status == ScanStatus.PASSED
    assert result.findings_count == 0
    assert result.highest_severity == SecuritySeverity.NONE
    assert result.should_block_release is False


def test_bandit_parser_high_severity_blocks_release():
    raw = {
        "results": [
            {
                "test_id": "B102",
                "test_name": "exec_used",
                "issue_severity": "HIGH",
                "issue_confidence": "HIGH",
                "issue_text": "Use of exec detected.",
                "filename": "sample_app/bad_code.py",
                "line_number": 42,
                "code": "exec('import os; os.system(api_key)')",
            }
        ]
    }
    result = BanditParser.parse(raw)
    assert result.status == ScanStatus.FAILED
    assert result.highest_severity == SecuritySeverity.HIGH
    assert result.should_block_release is True
    assert len(result.findings) == 1
    assert result.findings[0].rule_id == "B102"
    assert result.findings[0].file_path == "sample_app/bad_code.py"


def test_pip_audit_parser_vulnerabilities():
    raw = {
        "dependencies": [
            {
                "name": "insecure-package",
                "version": "1.0.0",
                "vulns": [
                    {
                        "id": "PYSEC-2024-9999",
                        "description": "Remote code execution flaw in parser",
                        "fix_versions": ["1.0.1"],
                    }
                ],
            }
        ]
    }
    result = PipAuditParser.parse(raw)
    assert result.status == ScanStatus.FAILED
    assert result.highest_severity == SecuritySeverity.HIGH
    assert result.should_block_release is True
    assert result.findings_count == 1
    assert "insecure-package" in result.findings[0].title
    assert result.findings[0].rule_id == "PYSEC-2024-9999"


def test_gitleaks_parser_secret_redaction_and_critical_severity():
    """
    CRITICAL PRIVACY TEST: Ensure secrets are never exposed in findings
    and are always sanitized to [REDACTED_SECRET].
    """
    raw = [
        {
            "RuleID": "github-pat",
            "Description": "GitHub Personal Access Token",
            "File": "config/secrets.py",
            "StartLine": 14,
            "Secret": "ghp_RealSecretToken1234567890abcdef",
        }
    ]
    result = GitleaksParser.parse(raw)
    assert result.status == ScanStatus.FAILED
    assert result.highest_severity == SecuritySeverity.CRITICAL
    assert result.should_block_release is True
    assert result.findings_count == 1

    finding = result.findings[0]
    # Verify raw secret is NOT present in any attribute
    assert "ghp_RealSecretToken1234567890abcdef" not in finding.description
    assert "ghp_RealSecretToken1234567890abcdef" not in finding.title
    assert finding.redacted_snippet == "[REDACTED_SECRET]"


def test_unified_security_scanner():
    bandit_res = SecurityScanner.evaluate_scan("bandit", {"results": []})
    assert bandit_res.tool_name == "Bandit"

    pip_res = SecurityScanner.evaluate_scan("pip-audit", {"dependencies": []})
    assert pip_res.tool_name == "pip-audit"

    gitleaks_res = SecurityScanner.evaluate_scan("gitleaks", [])
    assert gitleaks_res.tool_name == "Gitleaks"
