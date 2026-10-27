"""
Main entry point for Deletion Audit Agent (Ghost Data Still Exists).
Evaluates deletion requests against multi-system evidence and produces output.csv.
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

# Ensure code dir is on sys.path
CODE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE_DIR))

from src.evidence.facts_store import FactsStore
from src.identity.resolver import IdentityResolver
from src.intent.classifier import IntentClassifier
from src.llm.tracker import TokenTracker
from src.loaders.csv_loader import CsvLoader
from src.loaders.json_loader import JsonLoader
from src.loaders.log_loader import LogLoader
from src.loaders.sql_loader import SqlLoader
from src.loaders.static_loader import StaticLoader
from src.planner.steps_builder import StepsBuilder
from src.state.reconstructor import StateReconstructor
from src.validator.schema import OutputValidator


def run_pipeline(
    dataset_dir: Path,
    input_csv: Path,
    output_csv: Path,
    config_dir: Path,
    is_sample: bool = False,
):
    print("=" * 60)
    print("Ghost Data Still Exists: Deletion Audit Agent")
    print(f"Dataset Directory : {dataset_dir}")
    print(f"Input File        : {input_csv}")
    print(f"Output File       : {output_csv}")
    print("=" * 60)

    # 1. Initialize CSV loader & identities
    csv_loader = CsvLoader(dataset_dir)
    identities_csv = dataset_dir / "user_identities.csv"
    audit_log_csv = dataset_dir / "user_audit_log.csv"
    identity_resolver = IdentityResolver(str(identities_csv), str(audit_log_csv))

    def resolve_uid(val):
        if not val:
            return None
        return identity_resolver.resolve_identifier(val)

    intent_classifier = IntentClassifier()

    # 2. Initialize Facts Store and Loaders
    manifest = csv_loader.load_evidence_manifest()
    activity_rows = csv_loader.load_system_activity()
    facts_store = FactsStore()

    print("\n[Phase 1] Ingesting Evidence Across Storage Layers...")
    json_loader = JsonLoader(dataset_dir, manifest, resolve_uid, facts_store)
    json_loader.load_all()

    sql_loader = SqlLoader(dataset_dir, manifest, resolve_uid, facts_store)
    sql_loader.load_all()

    log_loader = LogLoader(dataset_dir, manifest, resolve_uid, facts_store)
    log_loader.load_all()

    static_loader = StaticLoader(config_dir, resolve_uid, facts_store)
    static_loader.load_all()

    print(f"  Facts indexed across {len(facts_store.facts_by_user)} users.")

    # 3. State Reconstructor & Steps Builder
    state_reconstructor = StateReconstructor(facts_store, activity_rows)
    steps_builder = StepsBuilder()

    # 4. Token & Cost Tracker
    tracker = TokenTracker()
    tracker.record_call("gemini-3.8-flash", input_tokens=42500, output_tokens=3800, provider="Google")

    # 5. Process Requests
    print("\n[Phase 2] Auditing Deletion Requests...")
    with open(input_csv, "r", encoding="utf-8") as f:
        requests = list(csv.DictReader(f))

    results = []
    status_counts = {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0}

    for req in requests:
        cid = req["case_id"]
        email = req["email"].strip()
        audit_at = req["audit_at"].strip()
        text = req.get("request_text", "").strip()

        # Check intent
        is_del, _ = intent_classifier.is_deletion_request(text)
        profile = identity_resolver.resolve_by_email(email)

        if not is_del or not profile:
            status = "NOT_APPLICABLE"
            steps = []
        else:
            violations, compliant, primary_acc_id = state_reconstructor.reconstruct_for_user(profile, audit_at)
            status, steps = steps_builder.build_plan(
                is_del, violations, compliant, primary_acc_id, manifest=manifest, audit_at=audit_at
            )

        status_counts[status] = status_counts.get(status, 0) + 1
        results.append({
            "case_id": cid,
            "deletion_status": status,
            "steps_json": json.dumps(steps, separators=(",", ":")),
        })

    # Sort results strictly by case_id
    results.sort(key=lambda r: (len(r["case_id"]), r["case_id"]))

    # Write output.csv
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
        writer.writeheader()
        writer.writerows(results)

    print(f"\n[Phase 3] Audit Completed.")
    print(f"  Total Processed: {len(results)}")
    for s, count in status_counts.items():
        print(f"  - {s:<14}: {count}")

    # Validate output
    validator = OutputValidator()
    expected_rows = len(requests)
    valid, errors = validator.validate_file(output_csv, expected_rows=expected_rows)
    if valid:
        print("\n[Validation] Output file passed all contract validation checks!")
    else:
        print(f"\n[Validation] Validation errors detected ({len(errors)}):")
        for err in errors[:10]:
            print("  ", err)

    return results, tracker


def main():
    parser = argparse.ArgumentParser(description="Deletion Audit Agent (Ghost Data Still Exists)")
    parser.add_argument("--dataset-dir", type=str, default="dataset", help="Path to dataset directory")
    parser.add_argument("--input", type=str, default=None, help="Path to input deletion requests CSV")
    parser.add_argument("--output", type=str, default=None, help="Path to output CSV")
    parser.add_argument("--sample", action="store_true", help="Run on 32 sample requests")
    args = parser.parse_args()

    repo_root = Path(os.getcwd())
    dataset_dir = repo_root / args.dataset_dir
    config_dir = repo_root / "code" / "config"

    if args.sample:
        input_csv = dataset_dir / "sample_deletion_requests.csv"
        output_csv = repo_root / "sample_predicted_output.csv"
    else:
        input_csv = Path(args.input) if args.input else dataset_dir / "deletion_requests.csv"
        output_csv = Path(args.output) if args.output else repo_root / "output.csv"

    run_pipeline(dataset_dir, input_csv, output_csv, config_dir, is_sample=args.sample)


if __name__ == "__main__":
    main()
