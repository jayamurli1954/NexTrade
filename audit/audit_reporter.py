# audit/audit_reporter.py
"""
Readiness Certification Reporter for NexTrade (Sub-Phase 4I).
Produces Markdown readiness certificates and structured JSON reports for Phase 4J Controlled Live Staging.
"""
import json
from typing import Dict, Any

from contracts.audit_contracts import ReadinessAuditCertificate


class AuditReporter:
    """
    Generates human-readable Markdown and structured JSON readiness certificates.
    """

    @staticmethod
    def generate_markdown_certificate(record: ReadinessAuditCertificate) -> str:
        """
        Generates a Markdown readiness audit certificate.
        """
        lines = [
            f"# NexTrade Phase 4I — Live Readiness Audit Certificate",
            f"**Audit Certificate ID**: `{record.audit_id}`",
            f"**Audit Status Outcome**: `{record.audit_status.value}`",
            f"**Audited At**: `{record.audited_at.isoformat()}`",
            f"**Verified 4H Evidence Hash**: `{record.verified_evidence_hash}`",
            f"**Audit Deterministic Hash**: `{record.audit_hash}`",
            "",
            "## 12 Mandatory Audit Checkpoints (R1–R12)",
        ]
        for check in record.check_results:
            status_icon = "PASS 🟢" if check.passed else "FAIL 🔴"
            lines.append(f"- **[{check.check_id}] {check.name}**: {status_icon}")
            lines.append(f"  - *Category*: `{check.category}`")
            lines.append(f"  - *Details*: {check.details}")

        lines.extend([
            "",
            "## Git Release Stack Provenance",
        ])
        for tag, commit in record.git_release_stack.items():
            lines.append(f"- `{tag}` -> `{commit}`")

        lines.extend([
            "",
            "## Audit Decision Reasons",
        ])
        for reason in record.audit_reasons:
            lines.append(f"- {reason}")

        lines.extend([
            "",
            "> [!IMPORTANT]",
            "> **Invariant 4I-P1 Notice**: This certificate certifies live readiness ONLY. It MUST NOT enable live trading, change environment, or dispatch broker orders. Live staging requires Phase 4J authorization.",
        ])

        return "\n".join(lines)

    @staticmethod
    def generate_json_certificate(record: ReadinessAuditCertificate) -> str:
        """
        Generates a JSON formatted readiness audit certificate.
        """
        data = {
            "audit_id": record.audit_id,
            "promotion_certificate_id": record.promotion_certificate_id,
            "verified_evidence_hash": record.verified_evidence_hash,
            "audit_status": record.audit_status.value,
            "audit_hash": record.audit_hash,
            "audited_at": record.audited_at.isoformat(),
            "git_release_stack": record.git_release_stack,
            "check_results": [
                {
                    "check_id": c.check_id,
                    "category": c.category,
                    "name": c.name,
                    "passed": c.passed,
                    "details": c.details
                }
                for c in record.check_results
            ],
            "audit_reasons": record.audit_reasons
        }
        return json.dumps(data, indent=2)
