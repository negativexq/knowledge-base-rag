import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class SSEEvent:
    event: str
    data: dict


def parse_sse_lines(lines: Iterable[str]) -> Iterator[SSEEvent]:
    """Parse raw SSE lines (as yielded by httpx's line iterator) into
    structured events, matching the subset of the SSE spec app/api/chat.py
    actually emits: an optional `event: <name>` line followed by one
    `data: <json>` line, terminated by a blank line. Lines with no
    `event:` default to "message" (the SSE spec's default event type).
    """
    event_type = "message"
    data_lines: list[str] = []

    for line in lines:
        line = line.rstrip("\n")
        if line == "":
            if data_lines:
                yield SSEEvent(event=event_type, data=json.loads("\n".join(data_lines)))
            event_type = "message"
            data_lines = []
            continue

        if line.startswith("event:"):
            event_type = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())

    if data_lines:
        yield SSEEvent(event=event_type, data=json.loads("\n".join(data_lines)))
