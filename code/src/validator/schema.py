"""
Schema and Output Validator
Validates output CSV against challenge constraints.
"""

import csv
import json
from pathlib import Path
from typing import List, Tuple

VALID_PHASES = ["FINDING", "REMEDIATION", "VERIFICATION"]
VALID_OPERATIONS = {
    "FINDING": [
        "REPORT_REMAINING_RECORD",
        "REPORT_EXPOSED_PII",
        "REPORT_ACTIVE_DATA_FLOW",
        "REPORT_RESTORE_RISK",
    ],
    "REMEDIATION": [
        "DISABLE_DATA_FLOW",
        "BLOCK_RESTORE",
        "DELETE_RECORD",
        "REDACT_RECORD",
        "ANONYMIZE_RECORD",
    ],
    "VERIFICATION": [
        "VERIFY_RECORD_ABSENT",
        "VERIFY_RECORD_PRESENT",
        "VERIFY_RECORD_REDACTED",
        "VERIFY_RECORD_ANONYMIZED",
        "VERIFY_DATA_FLOW_DISABLED",
        "VERIFY_RESTORE_BLOCKED",
    ],
}
VALID_STATES = ["PRESENT", "ABSENT", "REDACTED", "ANONYMIZED", "ACTIVE", "BLOCKED", "DISABLED"]


class OutputValidator:
    def validate_file(self, csv_path: Path, expected_rows: Optional[int] = None) -> Tuple[bool, List[str]]:
        errors = []
        if not csv_path.exists():
            return False, [f"File {csv_path} does not exist"]

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            if fieldnames != ["case_id", "deletion_status", "steps_json"]:
                errors.append(f"Invalid columns: expected ['case_id', 'deletion_status', 'steps_json'], got {fieldnames}")

            rows = list(reader)

        if expected_rows is not None and len(rows) != expected_rows:
            errors.append(f"Row count mismatch: expected {expected_rows}, got {len(rows)}")

        for idx, row in enumerate(rows, 1):
            cid = row.get("case_id", "")
            status = row.get("deletion_status", "")
            steps_str = row.get("steps_json", "")

            if status not in ["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]:
                errors.append(f"Row {idx} ({cid}): invalid status '{status}'")

            try:
                steps = json.loads(steps_str)
            except Exception as e:
                errors.append(f"Row {idx} ({cid}): invalid JSON in steps_json: {e}")
                continue

            if not isinstance(steps, list):
                errors.append(f"Row {idx} ({cid}): steps_json must be a JSON array")
                continue

            if status == "NOT_APPLICABLE" and len(steps) != 0:
                errors.append(f"Row {idx} ({cid}): NOT_APPLICABLE must have empty steps_json '[]'")

            # Validate each step
            last_phase_idx = -1
            for s_idx, step in enumerate(steps, 1):
                if step.get("step_no") != s_idx:
                    errors.append(f"Row {idx} ({cid}): step_no mismatch: expected {s_idx}, got {step.get('step_no')}")

                phase = step.get("phase")
                op = step.get("operation")
                state = step.get("state")
                ev_id = step.get("evidence_id")

                if phase not in VALID_PHASES:
                    errors.append(f"Row {idx} ({cid}) step {s_idx}: invalid phase '{phase}'")
                else:
                    curr_phase_idx = VALID_PHASES.index(phase)
                    if curr_phase_idx < last_phase_idx:
                        errors.append(f"Row {idx} ({cid}) step {s_idx}: phase '{phase}' appeared after later phase")
                    last_phase_idx = curr_phase_idx

                    if op not in VALID_OPERATIONS.get(phase, []):
                        errors.append(f"Row {idx} ({cid}) step {s_idx}: invalid op '{op}' for phase '{phase}'")

                if state not in VALID_STATES:
                    errors.append(f"Row {idx} ({cid}) step {s_idx}: invalid state '{state}'")

                if status == "COMPLETE" and not ev_id:
                    errors.append(f"Row {idx} ({cid}) step {s_idx}: COMPLETE verifications must cite evidence_id")

        return len(errors) == 0, errors
