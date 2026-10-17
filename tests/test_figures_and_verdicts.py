"""Two more validator blocks from the luna rerun of the 39 blocked rows:

- The model restated table figures in another scale ("$1.383 billion" for a
  "1,383" in millions, 1013/1071/1078). The locale guard rightly reads
  "1.383" against "1,383" as ambiguous; the fix is the prompt: figures are
  copied as the cited unit prints them.
- A yes/no answer opening with "No." was blocked because "No" was compared
  as a BOOLEAN value the support never prints (516). A leading verdict judges
  the question; it is compared only when the cited support itself states a
  boolean ("enabled: false"), so a wrong "Yes" on a config value still
  conflicts."""

from app.evaluation.critical_validator_runtime import audit_critical_value
from app.llm.structured_output import SUPPORT_ID_OUTPUT_INSTRUCTIONS

MARKETS = "CA03 Sacramento County | CA04 San Francisco | CA11 San Mateo County"


def test_the_model_is_told_to_copy_figures_as_the_unit_prints_them():
    assert "exactly as the cited unit prints" in SUPPORT_ID_OUTPUT_INSTRUCTIONS
    assert "$1,383 million" in SUPPORT_ID_OUTPUT_INSTRUCTIONS


def test_a_leading_no_verdict_is_not_a_value_the_support_must_print():
    claim = (
        "No. CA03 is Sacramento County; the San Francisco Bay Area markets are CA04 through CA11."
    )

    result = audit_critical_value(claim, [MARKETS])

    assert result["validator_outcome"] == "PASS"
    assert result["skip_verdict_count"] == 1


def test_a_leading_verdict_is_compared_when_the_support_states_a_boolean():
    claim = "Yes, response caching is enabled by default."

    result = audit_critical_value(claim, ["response_cache_enabled: false (default)"])

    assert result["validator_outcome"] != "PASS"
    assert result["skip_verdict_count"] == 0


def test_a_no_inside_the_answer_is_not_a_verdict():
    result = audit_critical_value("CA03 is no Bay Area market.", [MARKETS])

    assert result["skip_verdict_count"] == 0
