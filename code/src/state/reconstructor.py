"""
State Reconstructor
Reconstructs the ground-truth state of each resource belonging to an identity at audit_at.
"""

import re
from typing import Dict, List, Optional, Set, Tuple

from src.evidence.facts_store import Fact, FactsStore
from src.identity.resolver import IdentityProfile


class StateReconstructor:
    def __init__(self, facts_store: FactsStore, activity_rows: List[Dict[str, str]]):
        self.facts_store = facts_store
        self.activity_rows = activity_rows

    def reconstruct_for_user(self, profile: IdentityProfile, audit_at: str) -> Tuple[List[Fact], List[Fact], Optional[str]]:
        """
        Returns (violations, compliant_facts, primary_account_id).
        """
        uid = profile.user_id
        facts = self.facts_store.get_facts_for_user(uid, audit_at)

        # Group facts by (system_id, resource_id) and take the most recent observation <= audit_at
        facts_by_res: Dict[Tuple[str, str], List[Fact]] = {}
        for f in facts:
            facts_by_res.setdefault((f.system_id, f.resource_id), []).append(f)

        latest_facts: Dict[Tuple[str, str], Fact] = {}
        for k, flist in facts_by_res.items():
            # Sort by captured_at descending
            flist.sort(key=lambda x: x.captured_at, reverse=True)
            latest_facts[k] = flist[0]

        violations: List[Fact] = []
        compliant: List[Fact] = []
        primary_account_id: Optional[str] = None

        for (sys_id, res_id), fact in latest_facts.items():
            if sys_id == "account_service":
                primary_account_id = res_id
                if fact.state == "PRESENT":
                    violations.append(fact)
                else:
                    compliant.append(fact)
            elif sys_id == "search_service":
                if fact.state == "PRESENT":
                    violations.append(fact)
                else:
                    compliant.append(fact)
            elif sys_id == "export_service":
                if fact.state == "PRESENT":
                    violations.append(fact)
                else:
                    compliant.append(fact)
            elif sys_id == "backup_service":
                if fact.state == "ACTIVE":
                    violations.append(fact)
                else:
                    compliant.append(fact)
            elif sys_id == "integration_service":
                if fact.state == "ACTIVE":
                    violations.append(fact)
                else:
                    compliant.append(fact)
            elif sys_id == "support_platform":
                if fact.is_pii_exposed or fact.state == "PRESENT":
                    violations.append(fact)
                else:
                    compliant.append(fact)
            elif sys_id == "analytics_platform":
                if fact.is_pii_exposed or fact.state == "PRESENT":
                    violations.append(fact)
                else:
                    compliant.append(fact)
            elif sys_id == "identity_service":
                if fact.is_pii_exposed or fact.state == "PRESENT":
                    violations.append(fact)
                else:
                    compliant.append(fact)
            elif sys_id in ["security_service", "legal_retention_service"]:
                compliant.append(fact)

        # Fallback for primary_account_id if not observed directly in evidence
        if not primary_account_id:
            # Check system_activity.csv for account_XXXX
            for act in self.activity_rows:
                if act.get("event_time", "") <= audit_at:
                    res = act.get("resource_id", "")
                    details = act.get("details", "")
                    if res.startswith("account_"):
                        is_uid_match = bool(uid and re.search(r'\b' + re.escape(uid) + r'\b', details))
                        is_email_match = any(re.search(r'(?i)\b' + re.escape(e) + r'\b', details) for e in profile.emails)
                        if is_uid_match or is_email_match:
                            primary_account_id = res
                            break
            # Fallback for user_id to account_id
            if not primary_account_id and uid.startswith("user_"):
                try:
                    num = int(uid.split("_")[1])
                    if num < 100:
                        primary_account_id = f"account_{num:03d}"
                    else:
                        primary_account_id = f"account_{num}"
                except Exception:
                    primary_account_id = f"account_{uid}"

        return violations, compliant, primary_account_id
