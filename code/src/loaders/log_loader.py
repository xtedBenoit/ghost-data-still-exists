"""
Log Evidence Loader
Loads observability logs, service readback traces, and handover text into FactsStore.
"""

import json
import re
from pathlib import Path
from typing import Callable, Dict, Optional

from src.evidence.facts_store import Fact, FactsStore
from src.loaders.json_loader import normalize_sys_id


class LogLoader:
    def __init__(self, dataset_dir: Path, manifest: Dict[str, Dict[str, str]], resolve_uid: Callable[[Optional[str]], Optional[str]], facts_store: FactsStore):
        self.dataset_dir = dataset_dir
        self.manifest = manifest
        self.resolve_uid = resolve_uid
        self.facts_store = facts_store

    def load_all(self):
        # 1. Parse evidence_03 (customer_account_handover_20261001.txt)
        handover_path = self.dataset_dir / "evidence" / "records" / "customer_account_handover_20261001.txt"
        if handover_path.exists():
            try:
                with open(handover_path, "r", encoding="utf-8") as hf:
                    for line in hf:
                        line = line.strip()
                        if not line.startswith("- "):
                            continue
                        parts = [p.strip() for p in line[2:].split("|")]
                        if len(parts) >= 6:
                            ts, sys_id, res_id, rec_type, status, ident = parts[:6]
                            uid = self.resolve_uid(ident)
                            sys_id = normalize_sys_id(sys_id)
                            if status == "NOT_FOUND":
                                self.facts_store.add_fact(Fact("evidence_03", "2026-10-01T12:00:00Z", sys_id, res_id, rec_type, "ABSENT", user_id=uid))
                            elif status == "IDENTIFIABLE":
                                self.facts_store.add_fact(Fact("evidence_03", "2026-10-01T12:00:00Z", sys_id, res_id, rec_type, "PRESENT", user_id=uid, is_pii_exposed=True))
                            elif status == "ANONYMIZED":
                                self.facts_store.add_fact(Fact("evidence_03", "2026-10-01T12:00:00Z", sys_id, res_id, rec_type, "ANONYMIZED", user_id=uid, is_pii_exposed=False))
                            elif status == "ACTIVE":
                                self.facts_store.add_fact(Fact("evidence_03", "2026-10-01T12:00:00Z", sys_id, res_id, rec_type, "ACTIVE", user_id=uid))
                            elif status == "BLOCKED":
                                self.facts_store.add_fact(Fact("evidence_03", "2026-10-01T12:00:00Z", sys_id, res_id, rec_type, "BLOCKED", user_id=uid))
                            elif status == "DISABLED":
                                self.facts_store.add_fact(Fact("evidence_03", "2026-10-01T12:00:00Z", sys_id, res_id, rec_type, "DISABLED", user_id=uid))
                            elif status == "REDACTED":
                                self.facts_store.add_fact(Fact("evidence_03", "2026-10-01T12:00:00Z", sys_id, res_id, rec_type, "REDACTED", user_id=uid, is_pii_exposed=False))
                            elif status == "FOUND":
                                self.facts_store.add_fact(Fact("evidence_03", "2026-10-01T12:00:00Z", sys_id, res_id, rec_type, "PRESENT", user_id=uid))
            except Exception:
                pass

        # 2. Parse all log files
        log_files = [m for m in self.manifest.values() if m["file_path"].endswith(".log")]
        for meta in log_files:
            fid = meta["file_id"]
            cap_at = meta.get("captured_at", "")
            p = self.dataset_dir / meta["file_path"]
            if not p.exists():
                continue
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as lf:
                    lines = lf.readlines()
                traces = {}
                for line in lines:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    # Check JSON line
                    if "{" in line_str and "}" in line_str:
                        json_part = line_str[line_str.find("{"):line_str.rfind("}")+1]
                        try:
                            ld = json.loads(json_part)
                            tr = ld.get("trace_id")
                            res = ld.get("resource_id")
                            svc = ld.get("service") or ld.get("logger")
                            ev = str(ld.get("event", ""))

                            ident = None
                            for k in ["lookup_key", "subject_key", "match_key", "correlation_key", "subject_ref", "customer_reference", "user_id", "email", "requester_email", "matched_value"]:
                                val = ld.get(k)
                                if val and str(val).lower() not in ["null", "none", ""]:
                                    ident = val
                                    break
                            if tr and ident:
                                traces.setdefault(tr, {})["ident"] = ident
                            if tr and res:
                                traces.setdefault(tr, {})["res"] = res
                            if tr and svc:
                                traces.setdefault(tr, {})["svc"] = svc

                            u_ident = ident or (traces.get(tr, {}).get("ident") if tr else None)
                            uid = self.resolve_uid(u_ident)
                            res_id = res or (traces.get(tr, {}).get("res") if tr else None)
                            sys_id = normalize_sys_id(svc or (traces.get(tr, {}).get("svc") if tr else ""))

                            if uid and res_id:
                                if "404" in str(ld.get("http_status")) or ld.get("rows") == "0" or ld.get("rows") == 0:
                                    self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "USER_PROFILE", "ABSENT", user_id=uid))
                                elif ld.get("eligible") == "true" and ld.get("deletion_block") == "false":
                                    self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "BACKUP_ARCHIVE", "ACTIVE", user_id=uid))
                                elif ld.get("enabled") == "true" or ld.get("enabled") is True:
                                    self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "ACTIVE_DATA_FLOW", "ACTIVE", user_id=uid))
                                elif "pii_scan" in ev or ld.get("detector") == "direct_identifier":
                                    self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "SUPPORT_MESSAGE", "PRESENT", user_id=uid, is_pii_exposed=True))
                                elif ld.get("result") == "hit" or ld.get("total_hits", 0) > 0 or ld.get("rows") == "1" or ld.get("rows") == 1:
                                    if "search" in sys_id:
                                        self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "SEARCH_INDEX_ENTRY", "PRESENT", user_id=uid))
                                    elif "analytics" in sys_id:
                                        self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "ANALYTICS_PROFILE", "PRESENT", user_id=uid))
                                    elif "support" in sys_id:
                                        self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "SUPPORT_MESSAGE", "PRESENT", user_id=uid, is_pii_exposed=True))
                                    elif "account" in sys_id:
                                        self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "USER_PROFILE", "PRESENT", user_id=uid))
                                    elif "security" in sys_id:
                                        self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "SECURITY_AUDIT_LOG", "PRESENT", user_id=uid))
                        except Exception:
                            pass
                    else:
                        # Syslog line
                        matches = re.findall(r'(\w+)=(?:"([^"]*)"|([^\s]+))', line_str)
                        kv = {m[0]: m[1] if m[1] else m[2] for m in matches}
                        tr = kv.get("trace_id")
                        res = kv.get("resource_id")
                        svc = kv.get("service")
                        ev = kv.get("event", "")
                        ident = None
                        for k in ["lookup_key", "subject_key", "match_key", "correlation_key", "subject_reference", "customer_reference", "user_id", "email", "requester_email", "matched_value"]:
                            val = kv.get(k)
                            if val and str(val).lower() not in ["null", "none", ""]:
                                ident = val
                                break
                        if tr and ident:
                            traces.setdefault(tr, {})["ident"] = ident
                        if tr and res:
                            traces.setdefault(tr, {})["res"] = res
                        if tr and svc:
                            traces.setdefault(tr, {})["svc"] = svc

                        u_ident = ident or (traces.get(tr, {}).get("ident") if tr else None)
                        uid = self.resolve_uid(u_ident)
                        res_id = res or (traces.get(tr, {}).get("res") if tr else None)
                        sys_id = normalize_sys_id(svc or (traces.get(tr, {}).get("svc") if tr else ""))

                        if uid and res_id:
                            if kv.get("http_status") == "404" or kv.get("rows") == "0":
                                self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "USER_PROFILE", "ABSENT", user_id=uid))
                            elif kv.get("eligible") == "true" and kv.get("deletion_block") == "false":
                                self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "BACKUP_ARCHIVE", "ACTIVE", user_id=uid))
                            elif kv.get("enabled") == "true":
                                self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "ACTIVE_DATA_FLOW", "ACTIVE", user_id=uid))
                            elif "pii_scan" in ev or kv.get("detector") == "direct_identifier":
                                self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "SUPPORT_MESSAGE", "PRESENT", user_id=uid, is_pii_exposed=True))
                            elif kv.get("marker_found") == "false" or kv.get("rows") == "1" or kv.get("result") == "hit":
                                if "support" in sys_id:
                                    self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "SUPPORT_MESSAGE", "PRESENT", user_id=uid))
                                elif "search" in sys_id:
                                    self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "SEARCH_INDEX_ENTRY", "PRESENT", user_id=uid))
                                elif "analytics" in sys_id:
                                    self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "ANALYTICS_PROFILE", "PRESENT", user_id=uid))
                                elif "account" in sys_id:
                                    self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "USER_PROFILE", "PRESENT", user_id=uid))
                                elif "security" in sys_id:
                                    self.facts_store.add_fact(Fact(fid, cap_at, sys_id, res_id, "SECURITY_AUDIT_LOG", "PRESENT", user_id=uid))
            except Exception:
                pass
