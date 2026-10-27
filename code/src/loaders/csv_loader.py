"""
CSV Loader
Loads participant-facing CSV files from dataset directory.
"""

import csv
from pathlib import Path
from typing import Dict, List


class CsvLoader:
    def __init__(self, dataset_dir: Path):
        self.dataset_dir = dataset_dir

    def load_identities(self) -> List[Dict[str, str]]:
        path = self.dataset_dir / "user_identities.csv"
        with open(path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def load_audit_log(self) -> List[Dict[str, str]]:
        path = self.dataset_dir / "user_audit_log.csv"
        with open(path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def load_system_activity(self) -> List[Dict[str, str]]:
        path = self.dataset_dir / "system_activity.csv"
        with open(path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def load_deletion_rules(self) -> List[Dict[str, str]]:
        path = self.dataset_dir / "deletion_rules.csv"
        with open(path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def load_evidence_manifest(self) -> Dict[str, Dict[str, str]]:
        path = self.dataset_dir / "evidence_files.csv"
        with open(path, "r", encoding="utf-8") as f:
            return {r["file_id"]: r for r in csv.DictReader(f)}

    def load_requests(self, filename: str = "deletion_requests.csv") -> List[Dict[str, str]]:
        path = self.dataset_dir / filename
        with open(path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
