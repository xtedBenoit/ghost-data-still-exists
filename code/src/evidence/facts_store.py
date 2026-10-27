"""
Facts Store
Maintains a normalized, temporal index of facts across all evidence sources.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class Fact:
    evidence_id: str
    captured_at: str
    system_id: str
    resource_id: str
    record_type: str
    state: str  # PRESENT, ABSENT, REDACTED, ANONYMIZED, ACTIVE, BLOCKED, DISABLED
    user_id: Optional[str] = None
    is_pii_exposed: bool = False
    details: dict = field(default_factory=dict)


class FactsStore:
    def __init__(self):
        # user_id -> List[Fact]
        self.facts_by_user: Dict[str, List[Fact]] = {}
        # resource_id -> List[Fact]
        self.facts_by_resource: Dict[str, List[Fact]] = {}
        # user_id -> set of known resource_ids
        self.user_to_resources: Dict[str, Set[str]] = {}
        # resource_id -> user_id
        self.resource_to_user: Dict[str, str] = {}

    def add_fact(self, fact: Fact):
        if fact.user_id:
            self.facts_by_user.setdefault(fact.user_id, []).append(fact)
            if fact.resource_id:
                self.user_to_resources.setdefault(fact.user_id, set()).add(fact.resource_id)
                self.resource_to_user[fact.resource_id] = fact.user_id
        if fact.resource_id:
            self.facts_by_resource.setdefault(fact.resource_id, []).append(fact)

    def link_resource_to_user(self, resource_id: str, user_id: str):
        if resource_id and user_id:
            self.user_to_resources.setdefault(user_id, set()).add(resource_id)
            self.resource_to_user[resource_id] = user_id
            # Also backfill user_id on any facts for this resource
            for f in self.facts_by_resource.get(resource_id, []):
                if not f.user_id:
                    f.user_id = user_id
                    self.facts_by_user.setdefault(user_id, []).append(f)

    def get_facts_for_user(self, user_id: str, audit_at: str) -> List[Fact]:
        facts = self.facts_by_user.get(user_id, [])
        # Also check resources linked to this user
        linked_res = self.user_to_resources.get(user_id, set())
        for res_id in linked_res:
            for f in self.facts_by_resource.get(res_id, []):
                if f not in facts:
                    facts.append(f)
        
        # Filter facts captured at or before audit_at
        return [f for f in facts if f.captured_at <= audit_at]
