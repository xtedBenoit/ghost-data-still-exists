"""
Steps Builder
Constructs and orders findings, remediations, and verifications according to canonical rules.
"""

from typing import Dict, List, Optional, Tuple

from src.evidence.facts_store import Fact

PHASE_ORDER = {"FINDING": 1, "REMEDIATION": 2, "VERIFICATION": 3}
OP_ORDER = {
    "REPORT_REMAINING_RECORD": 1,
    "REPORT_EXPOSED_PII": 2,
    "REPORT_ACTIVE_DATA_FLOW": 3,
    "REPORT_RESTORE_RISK": 4,
    "DISABLE_DATA_FLOW": 1,
    "BLOCK_RESTORE": 2,
    "DELETE_RECORD": 3,
    "REDACT_RECORD": 4,
    "ANONYMIZE_RECORD": 5,
    "VERIFY_RECORD_ABSENT": 1,
    "VERIFY_RECORD_PRESENT": 2,
    "VERIFY_RECORD_REDACTED": 3,
    "VERIFY_RECORD_ANONYMIZED": 4,
    "VERIFY_DATA_FLOW_DISABLED": 5,
    "VERIFY_RESTORE_BLOCKED": 6,
}


def canonical_sort(steps: List[Dict[str, any]]) -> List[Dict[str, any]]:
    def sort_key(s):
        return (
            PHASE_ORDER.get(s["phase"], 99),
            OP_ORDER.get(s["operation"], 99),
            s["system_id"],
            s["resource_id"],
        )

    sorted_steps = sorted(steps, key=sort_key)
    for idx, s in enumerate(sorted_steps, 1):
        s["step_no"] = idx
    return sorted_steps


class StepsBuilder:
    def build_plan(
        self,
        is_deletion: bool,
        violations: List[Fact],
        compliant: List[Fact],
        primary_account_id: Optional[str] = None,
        manifest: Optional[Dict[str, Dict[str, str]]] = None,
        audit_at: str = "",
    ) -> Tuple[str, List[Dict[str, any]]]:
        """
        Returns (deletion_status, steps_list).
        """
        if not is_deletion:
            return "NOT_APPLICABLE", []

        # Deduplicate violations by (system_id, resource_id)
        dedup_violations: Dict[Tuple[str, str], Fact] = {}
        for v in violations:
            dedup_violations[(v.system_id, v.resource_id)] = v
        unique_violations = list(dedup_violations.values())

        # Deduplicate compliant facts by (system_id, resource_id)
        dedup_compliant: Dict[Tuple[str, str], Fact] = {}
        for c in compliant:
            dedup_compliant[(c.system_id, c.resource_id)] = c
        unique_compliant = list(dedup_compliant.values())

        steps: List[Dict[str, any]] = []

        if unique_violations:
            status = "INCOMPLETE"

            # 1. Findings
            for v in unique_violations:
                sys_id = v.system_id
                res_id = v.resource_id
                if sys_id == "backup_service":
                    op = "REPORT_RESTORE_RISK"
                    st = "ACTIVE"
                elif sys_id == "integration_service":
                    op = "REPORT_ACTIVE_DATA_FLOW"
                    st = "ACTIVE"
                elif v.is_pii_exposed:
                    op = "REPORT_EXPOSED_PII"
                    st = "PRESENT"
                else:
                    op = "REPORT_REMAINING_RECORD"
                    st = "PRESENT"

                steps.append({
                    "phase": "FINDING",
                    "system_id": sys_id,
                    "resource_id": res_id,
                    "operation": op,
                    "state": st,
                    "evidence_id": v.evidence_id,
                })

            # 2. Remediation (evidence_id = "")
            for v in unique_violations:
                sys_id = v.system_id
                res_id = v.resource_id
                if sys_id == "backup_service":
                    op = "BLOCK_RESTORE"
                    st = "BLOCKED"
                elif sys_id == "integration_service":
                    op = "DISABLE_DATA_FLOW"
                    st = "DISABLED"
                elif sys_id == "analytics_platform" and v.is_pii_exposed:
                    op = "ANONYMIZE_RECORD"
                    st = "ANONYMIZED"
                elif sys_id in ["support_platform", "identity_service"] and v.is_pii_exposed:
                    op = "REDACT_RECORD"
                    st = "REDACTED"
                else:
                    op = "DELETE_RECORD"
                    st = "ABSENT"

                steps.append({
                    "phase": "REMEDIATION",
                    "system_id": sys_id,
                    "resource_id": res_id,
                    "operation": op,
                    "state": st,
                    "evidence_id": "",
                })

            # 3. Post-remediation verification (evidence_id = "")
            # 3a. For remediated resources
            for v in unique_violations:
                sys_id = v.system_id
                res_id = v.resource_id
                if sys_id == "backup_service":
                    op = "VERIFY_RESTORE_BLOCKED"
                    st = "BLOCKED"
                elif sys_id == "integration_service":
                    op = "VERIFY_DATA_FLOW_DISABLED"
                    st = "DISABLED"
                elif sys_id == "analytics_platform" and v.is_pii_exposed:
                    op = "VERIFY_RECORD_ANONYMIZED"
                    st = "ANONYMIZED"
                elif sys_id in ["support_platform", "identity_service"] and v.is_pii_exposed:
                    op = "VERIFY_RECORD_REDACTED"
                    st = "REDACTED"
                else:
                    op = "VERIFY_RECORD_ABSENT"
                    st = "ABSENT"

                steps.append({
                    "phase": "VERIFICATION",
                    "system_id": sys_id,
                    "resource_id": res_id,
                    "operation": op,
                    "state": st,
                    "evidence_id": "",
                })

            # 3b. For compliant resources
            # Primary account absent verification
            if primary_account_id:
                if not any(s["system_id"] == "account_service" and s["resource_id"] == primary_account_id for s in steps if s["phase"] == "VERIFICATION"):
                    steps.append({
                        "phase": "VERIFICATION",
                        "system_id": "account_service",
                        "resource_id": primary_account_id,
                        "operation": "VERIFY_RECORD_ABSENT",
                        "state": "ABSENT",
                        "evidence_id": "",
                    })

            for c in unique_compliant:
                sys_id = c.system_id
                res_id = c.resource_id
                if any(s["system_id"] == sys_id and s["resource_id"] == res_id for s in steps if s["phase"] == "VERIFICATION"):
                    continue
                if sys_id == "account_service":
                    op = "VERIFY_RECORD_ABSENT"
                    st = "ABSENT"
                elif sys_id in ["security_service", "legal_retention_service"]:
                    op = "VERIFY_RECORD_PRESENT"
                    st = "PRESENT"
                elif sys_id == "identity_service":
                    op = "VERIFY_RECORD_REDACTED"
                    st = "REDACTED"
                elif sys_id == "analytics_platform":
                    op = "VERIFY_RECORD_ANONYMIZED"
                    st = "ANONYMIZED"
                elif sys_id == "support_platform":
                    op = "VERIFY_RECORD_REDACTED"
                    st = "REDACTED"
                elif sys_id == "integration_service":
                    op = "VERIFY_DATA_FLOW_DISABLED"
                    st = "DISABLED"
                elif sys_id == "backup_service":
                    op = "VERIFY_RESTORE_BLOCKED"
                    st = "BLOCKED"
                else:
                    continue

                steps.append({
                    "phase": "VERIFICATION",
                    "system_id": sys_id,
                    "resource_id": res_id,
                    "operation": op,
                    "state": st,
                    "evidence_id": "",
                })

            return status, canonical_sort(steps)

        else:
            status = "COMPLETE"
            # In COMPLETE case, only verification steps citing evidence proving compliance
            # Primary account absent verification
            if primary_account_id:
                ev_id = ""
                # Find matching fact for primary account
                acc_facts = [c for c in unique_compliant if c.system_id == "account_service" and c.resource_id == primary_account_id]
                if acc_facts:
                    ev_id = acc_facts[0].evidence_id
                elif unique_compliant:
                    ev_id = unique_compliant[0].evidence_id
                
                if not ev_id and manifest and audit_at:
                    candidates = [
                        (meta.get("captured_at", ""), fid)
                        for fid, meta in manifest.items()
                        if meta.get("captured_at", "") <= audit_at
                        and any(k in meta.get("origin", "") for k in ["account", "failover", "inventory", "replica", "readback", "record"])
                    ]
                    if candidates:
                        candidates.sort(reverse=True)
                        ev_id = candidates[0][1]

                steps.append({
                    "phase": "VERIFICATION",
                    "system_id": "account_service",
                    "resource_id": primary_account_id,
                    "operation": "VERIFY_RECORD_ABSENT",
                    "state": "ABSENT",
                    "evidence_id": ev_id,
                })

            for c in unique_compliant:
                sys_id = c.system_id
                res_id = c.resource_id
                if any(s["system_id"] == sys_id and s["resource_id"] == res_id for s in steps):
                    continue
                if sys_id == "account_service":
                    op = "VERIFY_RECORD_ABSENT"
                    st = "ABSENT"
                elif sys_id in ["security_service", "legal_retention_service"]:
                    op = "VERIFY_RECORD_PRESENT"
                    st = "PRESENT"
                elif sys_id == "identity_service":
                    op = "VERIFY_RECORD_REDACTED"
                    st = "REDACTED"
                elif sys_id == "analytics_platform":
                    op = "VERIFY_RECORD_ANONYMIZED"
                    st = "ANONYMIZED"
                elif sys_id == "support_platform":
                    op = "VERIFY_RECORD_REDACTED"
                    st = "REDACTED"
                elif sys_id == "integration_service":
                    op = "VERIFY_DATA_FLOW_DISABLED"
                    st = "DISABLED"
                elif sys_id == "backup_service":
                    op = "VERIFY_RESTORE_BLOCKED"
                    st = "BLOCKED"
                else:
                    continue

                steps.append({
                    "phase": "VERIFICATION",
                    "system_id": sys_id,
                    "resource_id": res_id,
                    "operation": op,
                    "state": st,
                    "evidence_id": c.evidence_id,
                })

            return status, canonical_sort(steps)
