"""
Identity Resolver
Resolves current and historical identities (user_id, emails, phones, names, hashes)
from user_identities.csv and user_audit_log.csv.
"""

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class IdentityProfile:
    user_id: str
    emails: Set[str] = field(default_factory=set)
    phones: Set[str] = field(default_factory=set)
    names: Set[str] = field(default_factory=set)
    email_hashes: Set[str] = field(default_factory=set)
    primary_email: str = ""
    primary_phone: str = ""
    primary_name: str = ""
    updated_at: str = ""

    def matches(self, val: Optional[str]) -> bool:
        if not val:
            return False
        clean = str(val).strip().lower()
        if clean in {e.lower() for e in self.emails}:
            return True
        if clean == self.user_id.lower():
            return True
        if clean in {h.lower() for h in self.email_hashes}:
            return True
        raw_val = str(val).strip()
        if raw_val in self.phones or raw_val in self.names:
            return True
        return False


class IdentityResolver:
    def __init__(self, identities_csv: str, audit_log_csv: str): 
        self.identities_csv = identities_csv
        self.audit_log_csv = audit_log_csv
        self.profiles_by_user_id: Dict[str, IdentityProfile] = {}
        self.email_to_user_id: Dict[str, str] = {}
        self.hash_to_user_id: Dict[str, str] = {}
        self.phone_to_user_id: Dict[str, str] = {}
        self._load()

    def _compute_hash(self, email: str) -> str:
        return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()

    def _load(self):
        # 1. Load user_identities.csv
        with open(self.identities_csv, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                uid = row["user_id"].strip()
                email = row["email"].strip().lower()
                name = row["name"].strip()
                phone = row["phone"].strip()
                ehash = row["email_hash"].strip().lower()

                profile = IdentityProfile(
                    user_id=uid,
                    primary_email=email,
                    primary_phone=phone,
                    primary_name=name,
                    updated_at=row.get("updated_at", ""),
                )
                if email:
                    profile.emails.add(email)
                    self.email_to_user_id[email] = uid
                if name:
                    profile.names.add(name)
                if phone:
                    profile.phones.add(phone)
                    self.phone_to_user_id[phone] = uid
                if ehash:
                    profile.email_hashes.add(ehash)
                    self.hash_to_user_id[ehash] = uid
                elif email:
                    h = self._compute_hash(email)
                    profile.email_hashes.add(h)
                    self.hash_to_user_id[h] = uid

                self.profiles_by_user_id[uid] = profile

        # 2. Enrich with historical values from user_audit_log.csv
        with open(self.audit_log_csv, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                uid = row["user_id"].strip()
                field_name = row["field_name"].strip()
                old_val = row["old_value"].strip()
                new_val = row["new_value"].strip()

                if uid not in self.profiles_by_user_id:
                    self.profiles_by_user_id[uid] = IdentityProfile(user_id=uid)
                p = self.profiles_by_user_id[uid]

                if field_name == "email":
                    if old_val:
                        e_old = old_val.lower()
                        p.emails.add(e_old)
                        self.email_to_user_id[e_old] = uid
                        h_old = self._compute_hash(e_old)
                        p.email_hashes.add(h_old)
                        self.hash_to_user_id[h_old] = uid
                    if new_val:
                        e_new = new_val.lower()
                        p.emails.add(e_new)
                        self.email_to_user_id[e_new] = uid
                        h_new = self._compute_hash(e_new)
                        p.email_hashes.add(h_new)
                        self.hash_to_user_id[h_new] = uid
                elif field_name == "phone":
                    if old_val:
                        p.phones.add(old_val)
                        self.phone_to_user_id[old_val] = uid
                    if new_val:
                        p.phones.add(new_val)
                        self.phone_to_user_id[new_val] = uid
                elif field_name == "name":
                    if old_val:
                        p.names.add(old_val)
                    if new_val:
                        p.names.add(new_val)

    def resolve_identifier(self, val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        val_clean = str(val).strip()
        val_lower = val_clean.lower()
        if val_clean in self.profiles_by_user_id:
            return val_clean
        if val_lower in self.email_to_user_id:
            return self.email_to_user_id[val_lower]
        if val_lower in self.hash_to_user_id:
            return self.hash_to_user_id[val_lower]
        if val_clean in self.phone_to_user_id:
            return self.phone_to_user_id[val_clean]
        return None

    def resolve_by_email(self, email: str) -> Optional[IdentityProfile]:
        norm_email = email.strip().lower()
        uid = self.email_to_user_id.get(norm_email)
        if uid:
            return self.profiles_by_user_id.get(uid)
        
        # If not found directly, create an ad-hoc profile with that email
        ad_hoc = IdentityProfile(
            user_id="",
            primary_email=norm_email,
        )
        ad_hoc.emails.add(norm_email)
        ad_hoc.email_hashes.add(self._compute_hash(norm_email))
        return ad_hoc

    def resolve_by_user_id(self, user_id: str) -> Optional[IdentityProfile]:
        return self.profiles_by_user_id.get(user_id)
