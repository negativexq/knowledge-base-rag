"""Deterministic claim-to-selected-support lexical relevance checks.

This module deliberately provides a narrow application-side guard. It does
not claim semantic entailment: exact content-token coverage and the existing
claim-local critical-value guard must both pass.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Any

from app.evaluation.critical_values import claim_local_critical_value_audit

_TOKEN = re.compile(r"[\w]+(?:[./:+#-][\w]+)*", re.UNICODE)

# Negation terms are intentionally absent. A supported negative claim must be
# distinguishable from an unsupported statement of search failure by evidence.
_STOPWORDS = {
    # English
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "if",
    "in",
    "is",
    "it",
    "its",
    "may",
    "of",
    "on",
    "or",
    "should",
    "that",
    "the",
    "their",
    "there",
    "these",
    "this",
    "those",
    "to",
    "was",
    "were",
    "will",
    "with",
    "would",
    "you",
    "your",
    # Turkish
    "ama",
    "bir",
    "bu",
    "da",
    "de",
    "diye",
    "en",
    "gibi",
    "ile",
    "için",
    "icin",
    "ise",
    "mi",
    "mı",
    "mu",
    "mü",
    "olan",
    "olarak",
    "ve",
    "veya",
}


def content_tokens(text: str) -> tuple[str, ...]:
    """Return stable exact content tokens without stemming technical terms."""
    normalized = unicodedata.normalize("NFKC", text or "").casefold()
    return tuple(
        token
        for token in _TOKEN.findall(normalized)
        if token not in _STOPWORDS and len(token) > 1
    )


def audit_support_relevance(
    claim: str,
    support_texts: Sequence[str],
    *,
    coverage_threshold: float,
) -> dict[str, Any]:
    """Audit lexical support coverage plus critical-value consistency.

    No phrase blocklist, fuzzy matching, embeddings, stemming, gold labels, or
    judge outputs participate in the decision.
    """
    if not 0.0 <= coverage_threshold <= 1.0:
        raise ValueError("coverage_threshold must be between zero and one")
    claim_tokens = set(content_tokens(claim))
    support_tokens = set(content_tokens("\n".join(support_texts)))
    matched = claim_tokens & support_tokens
    coverage = len(matched) / len(claim_tokens) if claim_tokens else 0.0
    critical = claim_local_critical_value_audit(claim, support_texts)
    failures: list[str] = []
    if not claim_tokens or coverage < coverage_threshold:
        failures.append("SUPPORT_RELEVANCE_BELOW_THRESHOLD")
    if not critical["pass"]:
        failures.extend(critical["failure_codes"])
    return {
        "supported": not failures,
        "coverage_threshold": coverage_threshold,
        "coverage": coverage,
        "claim_content_tokens": sorted(claim_tokens),
        "support_content_tokens": sorted(support_tokens),
        "matched_content_tokens": sorted(matched),
        "unmatched_content_tokens": sorted(claim_tokens - support_tokens),
        "critical_value_audit": critical,
        "failure_codes": sorted(set(failures)),
        "blocklist_used": False,
        "normalization": "NFKC_CASEFOLD_EXACT_TOKEN_NO_STEM_TR_EN_STOPWORDS_NEGATION_PRESERVED",
    }
