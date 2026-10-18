"""Real PDF extraction plus agent admission, version and visual verification checks."""

import hashlib
import json

import fitz
import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app.evidence.pdf_structure import PdfStructure
from app.llm.agentic import AgentDependencies, EvidenceLedger, run_agent
from app.llm.visual_answer import PdfPages, PdfSnapshot
from app.retrieval.hybrid_search import SearchResult


@pytest.fixture
def pdf(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text((50, 60), "Revenue in millions; fiscal year 2021.")
    for x in (50, 200, 350):
        page.draw_line((x, 100), (x, 190))
    for y in (100, 130, 160, 190):
        page.draw_line((50, y), (350, y))
    for x, y, text in [
        (60, 120, "Region"),
        (210, 120, "2021"),
        (60, 150, "North"),
        (210, 150, "12"),
        (60, 180, "South"),
        (210, 180, "8"),
    ]:
        page.insert_text((x, y), text)
    page.insert_text((50, 240), "Table 1. Regional revenue")
    page.insert_text((50, 270), "Note: excludes discontinued operations.")
    doc.new_page()
    doc.set_toc([[1, "Revenue", 1]])
    content = doc.tobytes()
    doc.close()
    (tmp_path / "report.pdf").write_bytes(content)
    return tmp_path, content


def deps_for(pdf, *, budget=5000, version=None, **kwargs):
    root, content = pdf
    ledger = EvidenceLedger(lambda s: len(s.split()), budget)
    ledger.add(
        [
            SearchResult(
                id="initial",
                score=1,
                payload={
                    "text": "Regional revenue report.",
                    "source_type": "filesystem",
                    "source_id": "report_pdf",
                    "tenant_id": "a",
                    "page_number": 1,
                    "document_version": version or hashlib.sha256(content).hexdigest(),
                },
            )
        ]
    )
    return AgentDependencies(
        "What is the North revenue?", ledger, render_page=PdfPages(str(root)), **kwargs
    )


def returns(messages):
    return [p for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]


def refuse(info):
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"abstain": True})])


def test_pdf_structure_preserves_cells_context_and_pagination(pdf):
    structure = PdfStructure(PdfSnapshot("report_pdf", pdf[1]))
    listing = structure.list()
    assert listing["has_more"] and listing["next_page"] == 2
    assert listing["complete_figure_inventory"] is False
    table = next(e for e in listing["elements"] if e["kind"] == "table")
    result = structure.table(table["element_id"])
    assert result["header"] == ["Region", "2021"]
    assert result["rows"] == [["North", "12"], ["South", "8"]]
    assert "excludes discontinued" in result["context_text"]
    assert "2021: 12" in result["text"]
    assert not structure.list(page=2)["has_more"]
    element, png = structure.render(table["element_id"])
    assert element.page == 1 and png.startswith(b"\x89PNG")
    with pytest.raises(ValueError, match="UNKNOWN_ELEMENT_ID"):
        structure.element("../../secrets")


@pytest.mark.asyncio
async def test_agent_reads_table_as_citable_evidence(pdf):
    deps = deps_for(pdf)

    def model(messages, info):
        if not returns(messages):
            return ModelResponse(
                parts=[
                    ToolCallPart("inspect_table", {"support_id": "E1.S1", "element_id": "P1.T1"})
                ]
            )
        result = returns(messages)[0].content
        assert result["admitted"] and result["support_ids"][0] == "E2.S1"
        assert "excludes discontinued" in str(messages[0].parts)
        assert result["rows"][0] == ["North", "12"]
        return refuse(info)

    result = await run_agent(FunctionModel(model), deps)
    assert result.failure_code is None
    assert len(result.blocks) == 2
    assert result.blocks[1].payload["reading_method"] == "versioned_pdf_table"


@pytest.mark.asyncio
async def test_table_cells_never_bypass_evidence_budget(pdf):
    deps = deps_for(pdf, budget=48)

    def model(messages, info):
        if not returns(messages):
            return ModelResponse(
                parts=[
                    ToolCallPart("inspect_table", {"support_id": "E1.S1", "element_id": "P1.T1"})
                ]
            )
        result = returns(messages)[0].content
        assert result["admitted"] is False
        assert "rows" not in result and "context_text" not in result
        assert result["admission"]["budget_excluded_blocks"] == 1
        return refuse(info)

    result = await run_agent(FunctionModel(model), deps)
    assert result.failure_code is None
    assert len(result.blocks) == 1


async def test_table_is_found_on_the_support_page_without_listing_elements(pdf):
    deps = deps_for(pdf)

    def model(messages, info):
        if not returns(messages):
            return ModelResponse(parts=[ToolCallPart("inspect_table", {"support_id": "E1.S1"})])
        result = returns(messages)[0].content
        assert result["element_id"] == "P1.T1" and result["other_tables_on_page"] == []
        assert result["rows"][0] == ["North", "12"]
        return refuse(info)

    result = await run_agent(FunctionModel(model), deps)
    assert result.failure_code is None


@pytest.mark.asyncio
async def test_pdf_version_mismatch_is_recoverable_and_does_not_read_content(pdf):
    deps = deps_for(pdf, version="stale")
    calls = 0

    def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return ModelResponse(parts=[ToolCallPart("inspect_table", {"support_id": "E1.S1"})])
        assert "Regional revenue" not in str(messages[-1])
        return refuse(info)

    result = await run_agent(FunctionModel(model), deps)
    assert result.failure_code is None and not deps.pdf_structures
    assert calls == 2


class Vision:
    supports_structured = True
    supports_images = True

    def __init__(self, *, accepted=True):
        self.accepted = accepted
        self.calls = []

    async def chat_json(self, messages, **kwargs):
        self.calls.append(messages)
        if len(self.calls) == 1:
            return json.dumps(
                {
                    "answer": "12 million",
                    "page": 1,
                    "observation": "North 2021 revenue is 12",
                    "abstain": False,
                }
            )
        return json.dumps(
            {"shown_on_page": True, "meets_question": self.accepted, "reason": "checked"}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [True, False])
async def test_region_shows_full_page_and_crop_and_requires_separate_check(pdf, accepted):
    vision = Vision(accepted=accepted)
    deps = deps_for(pdf, provider=vision, visual_answers=True)
    deps.question = "What does the revenue chart show for North?"

    def model(messages, info):
        if not returns(messages):
            return ModelResponse(
                parts=[
                    ToolCallPart("inspect_region", {"support_id": "E1.S1", "element_id": "P1.T1"})
                ]
            )
        result = returns(messages)[0].content
        assert result["verified"] is accepted
        if accepted:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        info.output_tools[0].name,
                        {"abstain": False, "visual_reading_id": result["visual_reading_id"]},
                    )
                ]
            )
        return refuse(info)

    result = await run_agent(FunctionModel(model), deps)
    assert result.failure_code is None
    assert len(vision.calls) == 2
    for call in vision.calls:
        assert sum(p["type"] == "input_image" for p in call[1]["content"]) == 2
    assert (result.visual is not None) is accepted


@pytest.mark.asyncio
async def test_cached_pdf_structure_cannot_be_read_after_document_revocation(pdf):
    from pydantic_ai import ModelRetry

    from app.security.models import DocumentRules, RetrievalContext

    class Permissions:
        allow = True

        def rules(self):
            return DocumentRules(
                "restricted",
                frozenset({("filesystem", "report_pdf")}) if self.allow else frozenset(),
                frozenset(),
            )

    permissions = Permissions()
    deps = deps_for(pdf)
    deps.ledger.context = RetrievalContext("a", document_permissions=permissions)
    await deps.pdf_structure("E1.S1")
    assert deps.pdf_structures
    permissions.allow = False
    with pytest.raises(ModelRetry, match="UNKNOWN_SUPPORT_ID"):
        await deps.pdf_structure("E1.S1")


@pytest.mark.asyncio
async def test_pdf_tools_emit_content_free_spans(pdf, monkeypatch):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    from app.llm import agent_observability as obs

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("research-tools")
    monkeypatch.setattr(obs, "get_tracer", lambda _: tracer)

    def model(messages, info):
        if not returns(messages):
            return ModelResponse(
                parts=[
                    ToolCallPart("inspect_table", {"support_id": "E1.S1", "element_id": "P1.T1"})
                ]
            )
        return refuse(info)

    result = await run_agent(FunctionModel(model), deps_for(pdf))
    assert result.failure_code is None
    spans = exporter.get_finished_spans()
    tool = next(s for s in spans if s.name == "tool.inspect_table")
    assert tool.attributes["tool.added_blocks"] == 1
    attributes = str([dict(s.attributes) for s in spans])
    assert "North" not in attributes and "Revenue" not in attributes
    assert "excludes discontinued" not in attributes and "input_image" not in attributes
    provider.shutdown()


def test_ingestion_and_tool_table_extraction_share_a_process_lock(pdf, monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    from app.parsing.pdf_parser import extract_elements

    original = fitz.Page.find_tables
    mutex = Lock()
    active = 0
    maximum = 0

    def observed(page, *args, **kwargs):
        nonlocal active, maximum
        with mutex:
            active += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.01)
            return original(page, *args, **kwargs)
        finally:
            with mutex:
                active -= 1

    monkeypatch.setattr(fitz.Page, "find_tables", observed)
    structure = PdfStructure(PdfSnapshot("report_pdf", pdf[1]))
    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [
            pool.submit(structure.table, "P1.T1"),
            pool.submit(extract_elements, str(pdf[0] / "report.pdf")),
            pool.submit(structure.table, "P1.T1"),
            pool.submit(extract_elements, str(pdf[0] / "report.pdf")),
        ]
        results = [task.result() for task in tasks]
    assert maximum == 1
    assert results[0]["rows"] == [["North", "12"], ["South", "8"]]
    assert results[2]["rows"] == results[0]["rows"]
    assert any(e.kind == "table" for e in results[1])
