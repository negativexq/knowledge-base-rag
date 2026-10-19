"""A version the cited units print is supported, however many a claim names.

The version guard used to judge a claim by its first version only, call a
two-part version ("1.6", "8.5") ambiguous, and treat "7.5.2" and "7.5.2.0" as
different releases. TechQA answers that quoted their units word for word were
forced to abstain (the Packaging Utility fix version, the MQ resource-adapter
version map, the DataPower 7.5.2 SSH defaults).
"""

from __future__ import annotations

import pytest

from app.evaluation.critical_validator_architecture_v2 import audit_claim_architecture_v2


def outcome(claim: str, *support: str) -> str:
    return audit_claim_architecture_v2(claim, list(support))["v3"]["validator_outcome"]


def test_a_two_part_version_printed_in_the_unit_passes():
    assert (
        outcome(
            "The issue is fixed in Packaging Utility version 1.6.",
            "This issue has been fixed in Packaging Utility version 1.6.",
        )
        == "PASS"
    )


def test_every_version_of_a_version_map_printed_in_the_units_passes():
    claim = (
        "WAS 8.5 shipped with the WebSphere MQ 7.1 Resource Adapter; WAS 8.5.0.1 shipped "
        "with 7.1.0.1 and WAS 8.5.0.2 with 7.1.0.2."
    )
    support = (
        "WebSphere Application Server Version 8.5 ships with the WebSphere MQ 7.1 Resource "
        "Adapter. WAS 8.5.0.1 - WMQ 7.1.0.1. WAS 8.5.0.2 - WMQ 7.1.0.2."
    )
    assert outcome(claim, support) == "PASS"


def test_trailing_zero_components_name_the_same_release():
    assert (
        outcome(
            "In DataPower 7.5.2 and later, SSH defaults changed.",
            "The enable-legacy-kex command for the SSH server profile is available in 7.5.2.0.",
        )
        == "PASS"
    )


@pytest.mark.parametrize(
    ("claim", "support"),
    [
        (
            "The issue is fixed in Packaging Utility version 1.7.",
            "This issue has been fixed in Packaging Utility version 1.6.",
        ),
        ("The fix is included in release 7.5.3.", "The fix is included in release 7.5.2.0."),
        (
            "WAS 8.5 ships the 7.1 adapter and WAS 9.0 ships the 9.1 adapter.",
            "WebSphere Application Server Version 8.5 ships with the 7.1 adapter.",
        ),
    ],
)
def test_a_version_the_units_do_not_print_still_fails(claim, support):
    assert outcome(claim, support) != "PASS"


def test_a_negated_claim_about_a_printed_version_is_still_a_conflict():
    assert (
        outcome(
            "Version 8.5.0.2 does not support TLS 1.2.",
            "Version 8.5.0.2 supports TLS 1.2.",
        )
        == "REJECT"
    )


def test_an_unrelated_not_and_the_word_support_do_not_make_a_negated_claim():
    # "does not resolve" in the claim and "customer support" in a unit used to
    # trip the negation guard and force an abstention.
    claim = (
        "This issue is fixed in Packaging Utility version 1.6. If that does not resolve it, "
        "contact IBM customer support."
    )
    support = (
        "RESOLVING THE PROBLEM This issue has been fixed in Packaging Utility version 1.6.",
        "Otherwise contact IBM customer support.",
    )
    assert outcome(claim, *support) == "PASS"


def test_support_in_a_url_is_not_a_verb():
    claim = (
        "The document identifies Log File Agent Version 6.2.3.2 Interim Fix 07, but does not "
        "establish that this is the latest version."
    )
    support = (
        "Tivoli Log File Agent, Version 6.2.3.2 Interim Fix 07 "
        "[http://www-01.ibm.com/support/docview.wss?uid=swg24038012]"
    )
    assert outcome(claim, support) == "PASS"


# TechQA production-v1, re-audited on the current validator: Q018 and Q239
# were still forced to abstain with the right fact cited.


def test_a_compact_version_after_the_same_product_name_is_the_same_release():
    # IBM writes BPM 7.5.0.1 as "BPM 7501".
    claim = "BPM 7.5.0.1 did not account for acronyms belonging to archived snapshots."
    support = "Acronym generation code in BPM 7501 did not take into consideration archived ones."
    assert outcome(claim, support) == "PASS"


@pytest.mark.parametrize(
    ("claim", "support"),
    [
        # Another product's compact number is not this product's release.
        ("BPM 7.5.0.1 fixes it.", "Acronym generation code in WAS 7501 fixes it."),
        # Digits that do not spell the claimed release.
        ("BPM 7.5.0.1 fixes it.", "Acronym generation code in BPM 7502 fixes it."),
    ],
)
def test_a_compact_number_that_is_not_the_claimed_release_still_fails(claim, support):
    assert outcome(claim, support) != "PASS"


def test_version_specificity_follows_the_judged_version_not_a_path():
    # "platform_7.5.0_????" inside a path made the guard read "5" as the
    # claim's first version and call the claim ambiguous.
    claim = (
        "Delete the `.eclipse/ibm.software.delivery.platform_7.5.0_????` directory. "
        "The reference describes Rational Application Developer 7.5.2, not RFT 8.2."
    )
    support = (
        "Delete the user's .eclipse/ibm.software.delivery.platform_7.5.0_???? directory. "
        "Rational Application Developer for WebSphere Software 7.5.2 All Editions"
    )
    assert outcome(claim, support) == "PASS"
