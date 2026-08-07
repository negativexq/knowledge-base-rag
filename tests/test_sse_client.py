from app.ui.sse_client import SSEEvent, parse_sse_lines


def test_parses_default_message_event():
    lines = ['data: {"token": "Hello"}', ""]

    events = list(parse_sse_lines(lines))

    assert events == [SSEEvent(event="message", data={"token": "Hello"})]


def test_parses_named_event():
    lines = ["event: grounding", 'data: {"grounded": true, "citations_found": [[1, 0]]}', ""]

    events = list(parse_sse_lines(lines))

    assert events == [
        SSEEvent(event="grounding", data={"grounded": True, "citations_found": [[1, 0]]})
    ]


def test_parses_multiple_events_in_sequence():
    lines = [
        "event: metadata",
        'data: {"prompt_version": "v1"}',
        "",
        'data: {"token": "Hi"}',
        "",
        'data: {"token": " there"}',
        "",
        "event: grounding",
        'data: {"grounded": true, "citations_found": [], "ungrounded_citations": []}',
        "",
    ]

    events = list(parse_sse_lines(lines))

    assert [e.event for e in events] == ["metadata", "message", "message", "grounding"]
    assert events[1].data == {"token": "Hi"}
    assert events[2].data == {"token": " there"}


def test_handles_trailing_event_without_final_blank_line():
    lines = ['data: {"token": "x"}']

    events = list(parse_sse_lines(lines))

    assert events == [SSEEvent(event="message", data={"token": "x"})]


def test_ignores_blank_lines_between_events_with_no_pending_data():
    lines = ["", "", 'data: {"token": "x"}', ""]

    events = list(parse_sse_lines(lines))

    assert events == [SSEEvent(event="message", data={"token": "x"})]
