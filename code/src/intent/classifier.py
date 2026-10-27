"""
Intent Classifier
Determines whether a user request text authorizes deletion or is NOT_APPLICABLE.
Includes defensive filtering against prompt injections, adversarial text,
and multilingual data access / export requests (EN, FR, ES, DE, JA).
"""

import re
from typing import Tuple


class IntentClassifier:
    # Explicit non-deletion patterns across multiple languages
    EXPLICIT_NON_DELETION_PATTERNS = [
        # English
        "leave the account active",
        "not asking for deletion",
        "keep the account as it is",
        "do not close the account",
        "without removing any of my records",
        "marketing lists only",
        "not a request to erase",
        "leave my profile",
        "continue using the service",
        "don't delete",
        "dont delete",
        "not a deletion",
        "do not delete",
        "do not erase",
        "dont erase",
        "keep my account",
        "leave the account open",
        "export only",
        "download my data",
        "access request",
        "copy of my data",
        "copy of the information",
        "article 15",
        "art. 15",
        "art 15",

        # French
        "droit d'accès",
        "droit d'acces",
        "ne pas supprimer",
        "ne supprimez pas",
        "ne supprimez rien",
        "garder mon compte",
        "conserver mon compte",
        "copie de mes données",
        "copie de mes donnees",
        "rectification",

        # Spanish
        "no borrar",
        "no eliminar",
        "mantener mi cuenta",
        "conservar mi cuenta",
        "solicitud de acceso",
        "copia de mis datos",
        "descargar mis datos",

        # German
        "nicht löschen",
        "nicht loeschen",
        "bitte nicht löschen",
        "konto behalten",
        "auskunft",
        "auskunftsersuchen",
        "datenübertragbarkeit",
        "datenuebertragbarkeit",
        "nur datenexport",

        # Japanese
        "削除しないで",
        "削除は不要",
        "開示請求",
        "データのエクスポートのみ",
        "アカウントを保持",
        "削除しないでください",

        # Adversarial Prompt Injections / Jailbreaks
        "ignore previous instructions",
        "ignore all previous",
        "system override",
        "override deletion status",
        "ignore deletion rules",
        "output complete",
        "mark complete",
        "ignore rules",
    ]

    DELETION_AFFIRMATIVE_KEYWORDS = [
        "delete",
        "erasure",
        "erase",
        "remove my account",
        "close and delete",
        "supprimer",
        "löschen",
        "eliminar",
        "cancelar cuenta",
        "forget",
        "oubli",
        "vergessen",
        "excluir",
        "削除",
        "effacer",
    ]

    def is_deletion_request(self, text: str) -> Tuple[bool, str]:
        """
        Returns (is_deletion, reason).
        If False, deletion_status is NOT_APPLICABLE.
        """
        if not text:
            return False, "Empty request text"

        clean = text.lower()

        # Check explicit negative patterns (including adversarial injections)
        for pattern in self.EXPLICIT_NON_DELETION_PATTERNS:
            if pattern in clean:
                return False, f"Matched non-deletion pattern: '{pattern}'"

        # Check affirmative deletion terms
        has_affirmative = any(kw in clean for kw in self.DELETION_AFFIRMATIVE_KEYWORDS)
        if has_affirmative:
            return True, "Affirmative deletion request"

        # Default fallback
        return True, "Default affirmative"
