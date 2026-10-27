"""
Static Evidence Loader
Loads facts extracted from PDF documents and images into FactsStore.
"""

import json
from pathlib import Path
from typing import Callable, Dict, Optional

from src.evidence.facts_store import Fact, FactsStore


class StaticLoader:
    def __init__(self, config_dir: Path, resolve_uid: Callable[[Optional[str]], Optional[str]], facts_store: FactsStore):
        self.config_dir = config_dir
        self.resolve_uid = resolve_uid
        self.facts_store = facts_store

    def load_all(self):
        # 1. Image facts
        img_path = self.config_dir / "image_facts.json"
        if img_path.exists():
            try:
                with open(img_path, "r", encoding="utf-8") as f:
                    img_data = json.load(f)
                for fid, item in img_data.items():
                    cap_at = item.get("captured_at", "")
                    for rec in item.get("records", []):
                        uid = self.resolve_uid(rec.get("user_id")) or self.resolve_uid(rec.get("email"))
                        sys_id = rec.get("system_id")
                        res_id = rec.get("resource_id")
                        rec_type = rec.get("record_type")
                        state = rec.get("state")
                        pii = not rec.get("is_redacted", True) if "is_redacted" in rec else (not rec.get("is_anonymized", True) if "is_anonymized" in rec else False)
                        self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, rec_type, state, user_id=uid, is_pii_exposed=pii))
            except Exception:
                pass

        # 2. PDF facts
        pdf_path = self.config_dir / "pdf_facts.json"
        if pdf_path.exists():
            try:
                with open(pdf_path, "r", encoding="utf-8") as f:
                    pdf_data = json.load(f)
                for fid, item in pdf_data.items():
                    cap_at = item.get("captured_at", "")
                    for rec in item.get("records", []):
                        uid = self.resolve_uid(rec.get("user_id")) or self.resolve_uid(rec.get("email"))
                        sys_id = rec.get("system_id")
                        res_id = rec.get("resource_id")
                        rec_type = rec.get("record_type")
                        state = rec.get("state")
                        pii = not rec.get("is_redacted", True) if "is_redacted" in rec else False
                        self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, rec_type, state, user_id=uid, is_pii_exposed=pii))
            except Exception:
                pass
