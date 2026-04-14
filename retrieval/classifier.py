# retrieval/classifier.py
"""
Lightweight keyword-based domain classifier.
Returns a list of matched domains; falls back to ["general"] if nothing matches.
Deterministic and easy to inspect/extend.
"""
from typing import List

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "consent": [
        "consent", "informed consent", "participant consent",
        "recontact", "withdraw", "opt-out", "assent",
        "broad consent", "dynamic consent", "consent form",
    ],
    "data_access": [
        "data access", "access committee", "data use",
        "controlled access", "open access", "DAC", "DUO",
        "data sharing", "data transfer", "repository",
        "data use agreement", "DUA", "access request",
    ],
    "cross_border": [
        "cross-border", "transborder", "international transfer",
        "jurisdiction", "GDPR", "third country", "data export",
        "cross border", "federated", "multi-national",
    ],
    "privacy_security": [
        "privacy", "confidentiality", "anonymi", "pseudonymi",
        "de-identif", "encryption", "security", "data protection",
        "access control", "audit", "re-identification", "breach",
    ],
}


def classify_domains(text: str) -> List[str]:
    """Return matched domain labels for the given text."""
    lower = text.lower()
    matched = [
        domain
        for domain, keywords in DOMAIN_KEYWORDS.items()
        if any(kw.lower() in lower for kw in keywords)
    ]
    return matched if matched else ["general"]
