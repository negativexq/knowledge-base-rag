from app.retrieval.report import RetrievalReport, RetrievalStage, stage_timer


def test_stage_timer_records_a_stage_on_the_report():
    report = RetrievalReport()

    with stage_timer(report, "test_stage", model="fake") as timer:
        timer.candidates_in = 20
        timer.candidates_out = 5
        timer.top_score = 0.9

    assert len(report.stages) == 1
    stage = report.stages[0]
    assert stage.name == "test_stage"
    assert stage.candidates_in == 20
    assert stage.candidates_out == 5
    assert stage.top_score == 0.9
    assert stage.duration_ms >= 0
    assert stage.detail == {"model": "fake"}


def test_stage_timer_is_a_no_op_when_report_is_none():
    with stage_timer(None, "test_stage") as timer:
        timer.candidates_out = 5
    # must not raise — this is the path every non-UI caller of search()
    # takes, and it must cost nothing.


def test_stage_timer_does_not_record_when_the_block_raises():
    report = RetrievalReport()

    try:
        with stage_timer(report, "failing_stage"):
            raise ValueError("boom")
    except ValueError:
        pass

    assert report.stages == []


def test_retrieval_report_as_dict_includes_authorization_and_total_duration():
    report = RetrievalReport()
    report.acl_applied = True
    report.acl_tenant_id = "tenant-a"
    report.is_system_context = False
    report.user_filters_applied = True
    report.record(RetrievalStage(name="a", duration_ms=10.0))
    report.record(RetrievalStage(name="b", duration_ms=5.0))

    result = report.as_dict()

    assert result["authorization"] == {
        "acl_applied": True,
        "tenant_id": "tenant-a",
        "is_system_context": False,
        "user_filters_applied": True,
    }
    assert result["total_duration_ms"] == 15.0
    assert [s["name"] for s in result["stages"]] == ["a", "b"]


def test_a_stage_the_pipeline_did_not_run_is_absent_not_zero():
    """No reranker configured -> no "rerank" stage at all in the report
    — never a fabricated zero-duration placeholder."""
    report = RetrievalReport()
    report.record(RetrievalStage(name="hybrid_retrieval", duration_ms=10.0))

    names = [s.name for s in report.stages]

    assert "rerank" not in names
