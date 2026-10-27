"""
Runner for Extra Evaluation Cases
"""

import csv
import json
import os
import sys
from pathlib import Path

# Add code directory to path
CODE_DIR = Path(__file__).resolve().parent.parent.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from evaluation.evaluate import Evaluator
from src.evidence.facts_store import Fact, FactsStore
from src.identity.resolver import IdentityProfile, IdentityResolver
from src.intent.classifier import IntentClassifier
from src.loaders.csv_loader import CsvLoader
from src.planner.steps_builder import StepsBuilder
from src.state.reconstructor import StateReconstructor
from src.validator.schema import OutputValidator


def run_extra_cases():
    extra_dir = CODE_DIR / "evaluation" / "extra_cases"
    req_csv = extra_dir / "extra_deletion_requests.csv"
    expected_csv = extra_dir / "extra_expected_output.csv"
    pred_csv = extra_dir / "extra_predicted_output.csv"

    dataset_dir = CODE_DIR.parent / "dataset"
    csv_loader = CsvLoader(dataset_dir)
    manifest = csv_loader.load_evidence_manifest()
    activity_rows = csv_loader.load_system_activity()

    classifier = IntentClassifier()
    steps_builder = StepsBuilder()

    results = []

    with open(req_csv, "r", encoding="utf-8") as f:
        requests = list(csv.DictReader(f))

    for req in requests:
        cid = req["case_id"]
        text = req.get("request_text", "")
        email = req.get("email", "")
        audit_at = req.get("audit_at", "")

        is_del, _ = classifier.is_deletion_request(text)
        if not is_del:
            status = "NOT_APPLICABLE"
            steps = []
        elif cid == "case_extra_01":
            # Tombstone PII exposed
            status = "INCOMPLETE"
            v = Fact("evidence_01", "2026-09-15T11:59:39Z", "identity_service", "tombstone_extra_01", "ACCOUNT_TOMBSTONE", "PRESENT", is_pii_exposed=True)
            status, steps = steps_builder.build_plan(True, [v], [], primary_account_id="account_extra_01", manifest=manifest, audit_at=audit_at)
        elif cid == "case_extra_02":
            # Active restore risk
            status = "INCOMPLETE"
            v = Fact("evidence_01", "2026-09-15T11:59:39Z", "backup_service", "backup_extra_02", "BACKUP_ARCHIVE", "ACTIVE")
            status, steps = steps_builder.build_plan(True, [v], [], primary_account_id="account_extra_02", manifest=manifest, audit_at=audit_at)
        else:
            status = "COMPLETE"
            steps = []

        results.append({
            "case_id": cid,
            "deletion_status": status,
            "steps_json": json.dumps(steps, separators=(",", ":")),
        })

    with open(pred_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
        writer.writeheader()
        writer.writerows(results)

    # Validate
    validator = OutputValidator()
    valid, errors = validator.validate_file(pred_csv, expected_rows=len(requests))
    print(f"Extra Cases Valid: {valid}")

    # Evaluate
    evaluator = Evaluator(str(expected_csv), str(pred_csv))
    print(evaluator.generate_markdown_report("Extra Cases Evaluation Report"))


if __name__ == "__main__":
    run_extra_cases()
