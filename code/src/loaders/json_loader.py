"""
JSON Evidence Loader
Loads service resource exports, snapshot bundles, and JSON records into FactsStore.
"""

import json
from pathlib import Path
from typing import Callable, Dict, Optional

from src.evidence.facts_store import Fact, FactsStore


def normalize_sys_id(s: str) -> str:
    if not s:
        return ""
    sl = str(s).lower()
    if "support" in sl:
        return "support_platform"
    if "search" in sl:
        return "search_service"
    if "account" in sl:
        return "account_service"
    if "analytics" in sl:
        return "analytics_platform"
    if "backup" in sl:
        return "backup_service"
    if "integration" in sl:
        return "integration_service"
    if "security" in sl:
        return "security_service"
    if "export" in sl:
        return "export_service"
    if "identity" in sl:
        return "identity_service"
    if "legal" in sl:
        return "legal_retention_service"
    return s


class JsonLoader:
    def __init__(self, dataset_dir: Path, manifest: Dict[str, Dict[str, str]], resolve_uid: Callable[[Optional[str]], Optional[str]], facts_store: FactsStore):
        self.dataset_dir = dataset_dir
        self.manifest = manifest
        self.resolve_uid = resolve_uid
        self.facts_store = facts_store

    def load_all(self):
        for fid, meta in self.manifest.items():
            fpath = self.dataset_dir / meta["file_path"]
            origin = meta["origin"]
            if not fpath.name.endswith(".json"):
                continue
            if not fpath.exists():
                continue
            try:
                with open(fpath, "r", encoding="utf-8") as jf:
                    data = json.load(jf)
            except Exception:
                continue

            cap_at = meta.get("captured_at", "")

            # 1. Service Resource Exports
            if origin == "service_resource_export" and "service_exports" in data:
                exports = data["service_exports"]
                
                # account_service
                for item in exports.get("account_service", {}).get("profile_lookups", []):
                    res_id = item.get("resource_id")
                    code = item.get("status_code")
                    prof = item.get("profile") or {}
                    uid = self.resolve_uid(prof.get("customer_reference")) or self.resolve_uid(prof.get("email"))
                    state = "ABSENT" if code == 404 else "PRESENT"
                    self.facts_store.add_fact(Fact(fid, cap_at, "account_service", res_id, "USER_PROFILE", state, user_id=uid))

                # analytics_platform
                for item in exports.get("analytics_platform", {}).get("profiles", []):
                    res_id = item.get("resource_id")
                    uid = self.resolve_uid(item.get("customer_reference")) or self.resolve_uid(item.get("email"))
                    has_pii = bool(item.get("email") or item.get("phone"))
                    state = "PRESENT" if has_pii else "ANONYMIZED"
                    self.facts_store.add_fact(Fact(fid, cap_at, "analytics_platform", res_id, "ANALYTICS_PROFILE", state, user_id=uid, is_pii_exposed=has_pii))

                # backup_service
                for item in exports.get("backup_service", {}).get("restore_entries", []):
                    res_id = item.get("resource_id")
                    uid = self.resolve_uid(item.get("customer_reference")) or self.resolve_uid(item.get("customer_email"))
                    allowed = item.get("restore_allowed", False)
                    state = "ACTIVE" if allowed else "BLOCKED"
                    self.facts_store.add_fact(Fact(fid, cap_at, "backup_service", res_id, "BACKUP_ARCHIVE", state, user_id=uid))

                # export_service
                for item in exports.get("export_service", {}).get("exports", []):
                    res_id = item.get("resource_id")
                    uid = self.resolve_uid(item.get("customer_reference")) or self.resolve_uid(item.get("owner_email"))
                    self.facts_store.add_fact(Fact(fid, cap_at, "export_service", res_id, "USER_EXPORT", "PRESENT", user_id=uid))

                # integration_service
                for item in exports.get("integration_service", {}).get("connectors", []):
                    res_id = item.get("resource_id")
                    uid = self.resolve_uid(item.get("customer_reference")) or self.resolve_uid(item.get("customer_email"))
                    enabled = item.get("enabled", False)
                    state = "ACTIVE" if enabled else "DISABLED"
                    self.facts_store.add_fact(Fact(fid, cap_at, "integration_service", res_id, "ACTIVE_DATA_FLOW", state, user_id=uid))

                # search_service
                for item in exports.get("search_service", {}).get("index_queries", []):
                    res_id = item.get("resource_id")
                    hits = item.get("hits", {})
                    total = hits.get("total", 0)
                    uid = self.resolve_uid(item.get("query"))
                    if not uid and hits.get("documents"):
                        doc = hits["documents"][0]
                        uid = self.resolve_uid(doc.get("customer_reference")) or self.resolve_uid(doc.get("email"))
                    state = "PRESENT" if total > 0 else "ABSENT"
                    self.facts_store.add_fact(Fact(fid, cap_at, "search_service", res_id, "SEARCH_INDEX_ENTRY", state, user_id=uid))

                # security_service
                for item in exports.get("security_service", {}).get("audit_records", []):
                    res_id = item.get("resource_id")
                    uid = self.resolve_uid(item.get("subject_reference"))
                    self.facts_store.add_fact(Fact(fid, cap_at, "security_service", res_id, "SECURITY_AUDIT_LOG", "PRESENT", user_id=uid))

                # support_platform
                for item in exports.get("support_platform", {}).get("tickets", []):
                    res_id = item.get("resource_id")
                    uid = self.resolve_uid(item.get("customer_reference")) or self.resolve_uid(item.get("requester_email"))
                    has_pii = bool(item.get("requester_email") or item.get("requester_name") or item.get("requester_phone"))
                    state = "PRESENT" if has_pii else "REDACTED"
                    self.facts_store.add_fact(Fact(fid, cap_at, "support_platform", res_id, "SUPPORT_MESSAGE", state, user_id=uid, is_pii_exposed=has_pii))

            # 2. Snapshot bundles
            elif "snapshot_bundle" in origin or "snapshots" in data:
                for snap in data.get("snapshots", []):
                    store = normalize_sys_id(snap.get("data_store", ""))
                    for r in snap.get("records", []):
                        res_id = r.get("resource_id")
                        if store == "identity_service":
                            uid = self.resolve_uid(r.get("subject_reference"))
                            has_pii = any(r.get(k) for k in ["name", "email", "phone", "email_hash"])
                            state = "PRESENT" if has_pii else "REDACTED"
                            self.facts_store.add_fact(Fact(fid, cap_at, "identity_service", res_id, "ACCOUNT_TOMBSTONE", state, user_id=uid, is_pii_exposed=has_pii))
                        elif store == "security_service":
                            uid = self.resolve_uid(r.get("subject_reference"))
                            self.facts_store.add_fact(Fact(fid, cap_at, "security_service", res_id, "SECURITY_AUDIT_LOG", "PRESENT", user_id=uid))
                        elif store == "account_service":
                            uid = self.resolve_uid(r.get("customer_reference")) or self.resolve_uid(r.get("email"))
                            self.facts_store.add_fact(Fact(fid, cap_at, "account_service", res_id, "USER_PROFILE", "PRESENT", user_id=uid))
                        elif store == "search_service":
                            doc = r.get("document", {})
                            uid = self.resolve_uid(doc.get("customer_reference")) or self.resolve_uid(doc.get("email"))
                            self.facts_store.add_fact(Fact(fid, cap_at, "search_service", res_id, "SEARCH_INDEX_ENTRY", "PRESENT", user_id=uid))
                        elif store == "legal_retention_service":
                            uid = self.resolve_uid(r.get("subject_reference"))
                            self.facts_store.add_fact(Fact(fid, cap_at, "legal_retention_service", res_id, "LEGAL_HOLD_RECORD", "PRESENT", user_id=uid))

            # 3. Analytics report
            elif origin == "analytics_platform" and "reports" in data:
                for rep in data.get("reports", []):
                    res_id = rep.get("resource_id")
                    uid = self.resolve_uid(rep.get("customer_reference")) or self.resolve_uid(rep.get("email"))
                    has_pii = bool(rep.get("email") or rep.get("phone"))
                    state = "PRESENT" if has_pii else "ANONYMIZED"
                    self.facts_store.add_fact(Fact(fid, cap_at, "analytics_platform", res_id, "ANALYTICS_PROFILE", state, user_id=uid, is_pii_exposed=has_pii))

            # 4. Export jobs
            elif origin == "export_service":
                records = data.get("records", []) or data.get("export_jobs", [])
                for job in records:
                    res_id = job.get("resource_id")
                    uid = self.resolve_uid(job.get("customer_reference")) or self.resolve_uid(job.get("owner_email"))
                    self.facts_store.add_fact(Fact(fid, cap_at, "export_service", res_id, "USER_EXPORT", "PRESENT", user_id=uid))
