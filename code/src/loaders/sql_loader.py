"""
SQL Evidence Loader
Loads SQL database snapshots and replicas into SQLite and extracts facts.
"""

import json
import sqlite3
from pathlib import Path
from typing import Callable, Dict, Optional

from src.evidence.facts_store import Fact, FactsStore
from src.loaders.json_loader import normalize_sys_id


class SqlLoader:
    def __init__(self, dataset_dir: Path, manifest: Dict[str, Dict[str, str]], resolve_uid: Callable[[Optional[str]], Optional[str]], facts_store: FactsStore):
        self.dataset_dir = dataset_dir
        self.manifest = manifest
        self.resolve_uid = resolve_uid
        self.facts_store = facts_store

    def load_all(self):
        for fid, meta in self.manifest.items():
            fpath = self.dataset_dir / meta["file_path"]
            origin = meta["origin"]
            if not fpath.name.endswith(".sql"):
                continue
            if not fpath.exists():
                continue
            con = None
            try:
                con = sqlite3.connect(":memory:")
                with open(fpath, "r", encoding="utf-8") as sf:
                    con.executescript(sf.read())
                tables = [t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

                cap_at = meta.get("captured_at", "")

                # 1. Failover replica
                if "customer_profiles_failover_replica" in tables:
                    for row in con.execute("SELECT resource_id, user_id, email, account_status FROM customer_profiles_failover_replica").fetchall():
                        res_id, r_uid, r_email, status = row
                        uid = self.resolve_uid(r_uid) or self.resolve_uid(r_email)
                        self.facts_store.add_fact(Fact(fid, cap_at, "account_service", res_id, "USER_PROFILE", "PRESENT", user_id=uid))

                # 2. Inventory capture
                if origin == "customer_data_inventory_capture":
                    if "customer_profiles" in tables:
                        for row in con.execute("SELECT resource_id, customer_reference, email FROM customer_profiles").fetchall():
                            uid = self.resolve_uid(row[1]) or self.resolve_uid(row[2])
                            self.facts_store.add_fact(Fact(fid, cap_at, "account_service", row[0], "USER_PROFILE", "PRESENT", user_id=uid))
                    if "customer_analytics_profiles" in tables:
                        for row in con.execute("SELECT resource_id, customer_reference, email, phone FROM customer_analytics_profiles").fetchall():
                            uid = self.resolve_uid(row[1]) or self.resolve_uid(row[2])
                            has_pii = bool(row[2] or row[3])
                            state = "PRESENT" if has_pii else "ANONYMIZED"
                            self.facts_store.add_fact(Fact(fid, cap_at, "analytics_platform", row[0], "ANALYTICS_PROFILE", state, user_id=uid, is_pii_exposed=has_pii))
                    if "customer_search_documents" in tables:
                        for row in con.execute("SELECT resource_id, customer_reference, email FROM customer_search_documents").fetchall():
                            uid = self.resolve_uid(row[1]) or self.resolve_uid(row[2])
                            self.facts_store.add_fact(Fact(fid, cap_at, "search_service", row[0], "SEARCH_INDEX_ENTRY", "PRESENT", user_id=uid))
                    if "support_records" in tables:
                        for row in con.execute("SELECT resource_id, customer_reference, requester_email, requester_phone FROM support_records").fetchall():
                            uid = self.resolve_uid(row[1]) or self.resolve_uid(row[2])
                            has_pii = bool(row[2] or row[3])
                            state = "PRESENT" if has_pii else "REDACTED"
                            self.facts_store.add_fact(Fact(fid, cap_at, "support_platform", row[0], "SUPPORT_MESSAGE", state, user_id=uid, is_pii_exposed=has_pii))
                    if "customer_exports" in tables:
                        for row in con.execute("SELECT resource_id, customer_reference, owner_email FROM customer_exports").fetchall():
                            uid = self.resolve_uid(row[1]) or self.resolve_uid(row[2])
                            self.facts_store.add_fact(Fact(fid, cap_at, "export_service", row[0], "USER_EXPORT", "PRESENT", user_id=uid))
                    if "connector_subscriptions" in tables:
                        for row in con.execute("SELECT resource_id, customer_reference, customer_email, enabled FROM connector_subscriptions").fetchall():
                            uid = self.resolve_uid(row[1]) or self.resolve_uid(row[2])
                            state = "ACTIVE" if row[3] == 1 else "DISABLED"
                            self.facts_store.add_fact(Fact(fid, cap_at, "integration_service", row[0], "ACTIVE_DATA_FLOW", state, user_id=uid))
                    if "backup_restore_entries" in tables:
                        for row in con.execute("SELECT resource_id, customer_reference, customer_email, restore_allowed FROM backup_restore_entries").fetchall():
                            uid = self.resolve_uid(row[1]) or self.resolve_uid(row[2])
                            state = "ACTIVE" if row[3] == 1 else "BLOCKED"
                            self.facts_store.add_fact(Fact(fid, cap_at, "backup_service", row[0], "BACKUP_ARCHIVE", state, user_id=uid))
                    if "security_audit_records" in tables:
                        for row in con.execute("SELECT resource_id, subject_reference FROM security_audit_records").fetchall():
                            uid = self.resolve_uid(row[1])
                            self.facts_store.add_fact(Fact(fid, cap_at, "security_service", row[0], "SECURITY_AUDIT_LOG", "PRESENT", user_id=uid))

                # 3. Read replica & regional / reporting replicas
                replica_tables = [t for t in tables if "replica" in t]
                for tname in replica_tables:
                    cols = [c[1] for c in con.execute(f"PRAGMA table_info({tname})").fetchall()]
                    if "record_json" in cols:
                        for row in con.execute(f"SELECT resource_id, origin_system, record_json FROM {tname}").fetchall():
                            res_id, orig_sys, rec_str = row
                            try:
                                rec = json.loads(rec_str)
                                uid = self.resolve_uid(rec.get("customer_reference")) or self.resolve_uid(rec.get("user_id")) or self.resolve_uid(rec.get("email"))
                                orig_sys = normalize_sys_id(orig_sys)
                                if orig_sys == "account_service":
                                    self.facts_store.add_fact(Fact(fid, cap_at, "account_service", res_id, "USER_PROFILE", "PRESENT", user_id=uid))
                                elif orig_sys == "search_service":
                                    self.facts_store.add_fact(Fact(fid, cap_at, "search_service", res_id, "SEARCH_INDEX_ENTRY", "PRESENT", user_id=uid))
                                elif orig_sys == "analytics_platform":
                                    has_pii = bool(rec.get("email") or rec.get("phone"))
                                    state = "PRESENT" if has_pii else "ANONYMIZED"
                                    self.facts_store.add_fact(Fact(fid, cap_at, "analytics_platform", res_id, "ANALYTICS_PROFILE", state, user_id=uid, is_pii_exposed=has_pii))
                                elif orig_sys == "support_platform":
                                    has_pii = bool(rec.get("requester_email") or rec.get("requester_phone"))
                                    state = "PRESENT" if has_pii else "REDACTED"
                                    self.facts_store.add_fact(Fact(fid, cap_at, "support_platform", res_id, "SUPPORT_MESSAGE", state, user_id=uid, is_pii_exposed=has_pii))
                            except Exception:
                                pass

                # 4. Search primary capture
                if "search_documents_primary" in tables:
                    for row in con.execute("SELECT resource_id, email FROM search_documents_primary").fetchall():
                        uid = self.resolve_uid(row[1])
                        self.facts_store.add_fact(Fact(fid, cap_at, "search_service", row[0], "SEARCH_INDEX_ENTRY", "PRESENT", user_id=uid))
            except Exception:
                pass
            finally:
                if con:
                    try:
                        con.close()
                    except Exception:
                        pass
