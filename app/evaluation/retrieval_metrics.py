from dataclasses import dataclass

from app.llm.citation_location import location_for
from app.retrieval.hybrid_search import SearchResult

# (source_type, source_id, location) — the same triple app/llm/grounding.py
# checks real citations against, so a golden question's expected chunk and
# a retrieved chunk are compared using exactly one definition of "which
# chunk is this," not a separate one invented for evaluation.
Location = tuple[str, str, str]


@dataclass(frozen=True)
class RetrievalMetrics:
    precision: float
    recall: float
    retrieved_locations: list[Location]
    expected_locations: list[Location]


def _location(payload: dict) -> Location:
    return (payload["source_type"], payload["source_id"], location_for(payload))


def compute_retrieval_metrics(
    retrieved: list[SearchResult], expected_locations: list[Location]
) -> RetrievalMetrics:
    """Deterministic, non-judged retrieval metrics — golden questions carry
    exact ground-truth locations, so classic set-overlap precision/recall
    apply directly (unlike generation metrics, which need a judge because
    there's no ground-truth text to diff against).
    """
    retrieved_locations = [_location(result.payload) for result in retrieved]

    matched = sum(1 for loc in retrieved_locations if loc in expected_locations)
    precision = matched / len(retrieved_locations) if retrieved_locations else 0.0
    recall = (
        sum(1 for loc in expected_locations if loc in retrieved_locations) / len(expected_locations)
        if expected_locations
        else 0.0
    )

    return RetrievalMetrics(
        precision=precision,
        recall=recall,
        retrieved_locations=retrieved_locations,
        expected_locations=expected_locations,
    )
