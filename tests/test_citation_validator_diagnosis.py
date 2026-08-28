from scripts.diagnose_citation_validator import build_diagnosis, validate_inputs


def test_diagnosis_validates_existing_identity_without_inference():
    data = validate_inputs()
    assert data["metadata"]["generation_model"] == "qwen3.5:4b"
    assert len(data["results"]) == 36
    assert len(data["refinement"]) == 22


def test_rejected_historical_outputs_remain_unassessable():
    report = build_diagnosis()
    assert report["scope"]["new_generation_calls"] == 0
    assert report["validator"]["rejection_count"] == 7
    assert report["validator"]["content_unassessable_rejected"] == 7
    assert report["validator"]["raw_candidate_observable_among_rejected"] == 0


def test_citation_identity_and_source_alignment_are_separate():
    report = build_diagnosis()
    assert report["citation_identity"]["record_identity_pass"] == 33
    assert report["citation_support"]["definitely_supported_occurrences"] == 26
    assert report["source_alignment"]["source_alignment_failure_occurrences"] == 16


def test_multidoc_and_injection_findings_are_preserved():
    report = build_diagnosis()
    assert report["multidoc"]["n"] == 3
    assert report["multidoc"]["phase6_semantic_gate_answer"] == "0/3"
    assert report["injection"]["control_failures"] == 0
