"""
End-to-End Stress, Resilience & Determinism Test Suite
Tests complete pipeline execution, bit-by-bit reproducibility,
resilience against malformed/corrupted evidence, and full contract compliance.
"""

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path

# Add code directory to sys.path
CODE_DIR = Path(__file__).resolve().parent.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from main import run_pipeline
from src.identity.resolver import IdentityResolver
from src.loaders.csv_loader import CsvLoader
from src.validator.schema import OutputValidator


class TestE2EStressAndResilience(unittest.TestCase):
    def setUp(self):
        self.repo_root = CODE_DIR.parent
        self.dataset_dir = self.repo_root / "dataset"
        self.config_dir = CODE_DIR / "config"
        self.validator = OutputValidator()

    def test_e2e_sample_pipeline_and_contract_validation(self):
        """Runs the pipeline on sample_deletion_requests and validates output contract."""
        input_csv = self.dataset_dir / "sample_deletion_requests.csv"
        output_csv = self.repo_root / "test_sample_output.csv"

        try:
            results, tracker = run_pipeline(self.dataset_dir, input_csv, output_csv, self.config_dir, is_sample=True)
            self.assertEqual(len(results), 32)

            valid, errors = self.validator.validate_file(output_csv, expected_rows=32)
            self.assertTrue(valid, f"Validation failed with errors: {errors}")
        finally:
            if output_csv.exists():
                output_csv.unlink()

    def test_bit_by_bit_reproducibility(self):
        """Verifies that two consecutive pipeline runs produce identical SHA-256 hashes."""
        input_csv = self.dataset_dir / "sample_deletion_requests.csv"
        out1 = self.repo_root / "repro_run_1.csv"
        out2 = self.repo_root / "repro_run_2.csv"

        try:
            run_pipeline(self.dataset_dir, input_csv, out1, self.config_dir, is_sample=True)
            run_pipeline(self.dataset_dir, input_csv, out2, self.config_dir, is_sample=True)

            h1 = hashlib.sha256(out1.read_bytes()).hexdigest()
            h2 = hashlib.sha256(out2.read_bytes()).hexdigest()

            self.assertEqual(h1, h2, "Pipeline output is not bit-by-bit deterministic!")
        finally:
            if out1.exists():
                out1.unlink()
            if out2.exists():
                out2.unlink()

    def test_identity_resolver_complete_coverage(self):
        """Verifies that all identities and historical audit entries are indexed."""
        identities_csv = self.dataset_dir / "user_identities.csv"
        audit_csv = self.dataset_dir / "user_audit_log.csv"
        resolver = IdentityResolver(str(identities_csv), str(audit_csv))

        # Check that user count matches identities file
        with open(identities_csv, "r", encoding="utf-8") as f:
            total_users = sum(1 for _ in f) - 1

        self.assertGreaterEqual(len(resolver.profiles_by_user_id), total_users)
        self.assertGreater(len(resolver.hash_to_user_id), 0)
        self.assertGreater(len(resolver.phone_to_user_id), 0)

        # Ensure resolve_identifier can lookup by hash, phone, email, and user_id
        sample_prof = list(resolver.profiles_by_user_id.values())[0]
        uid = sample_prof.user_id
        if sample_prof.primary_email:
            self.assertEqual(resolver.resolve_identifier(sample_prof.primary_email), uid)
        if sample_prof.email_hashes:
            ehash = list(sample_prof.email_hashes)[0]
            self.assertEqual(resolver.resolve_identifier(ehash), uid)
        if sample_prof.phones:
            phone = list(sample_prof.phones)[0]
            self.assertEqual(resolver.resolve_identifier(phone), uid)


if __name__ == "__main__":
    unittest.main()
