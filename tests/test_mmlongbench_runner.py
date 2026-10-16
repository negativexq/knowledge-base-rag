"""Each benchmark manifest gets its own index: a collection, a registry and a
documents folder holding only that manifest's PDFs. A shared registry made a
new collection's documents look already ingested, and ingesting the shared
documents folder put the v2 PDFs into the 20-question pilot's index."""

from app.evaluation.mmlongbench import Manifest, ManifestFile
from scripts.benchmarks import run_mmlongbench_pilot as runner


def _manifest(*paths: str) -> Manifest:
    return Manifest(
        dataset="d",
        revision="r",
        files=tuple(ManifestFile(path=p, size=1) for p in paths),
        question_rows=(),
    )


def test_the_pilot_keeps_its_collection_and_v2_gets_its_own():
    assert runner.collection_for(runner.MANIFEST) == "kb_bench_mmlongbench"
    v2 = runner.ROOT / "artifacts" / "mmlongbench-v2" / "manifest.json"
    assert runner.collection_for(v2) == "kb_bench_mmlongbench_v2"


def test_a_chunking_challenger_gets_its_own_collection():
    v2 = runner.ROOT / "artifacts" / "mmlongbench-v2" / "manifest.json"
    assert runner.collection_for(v2, "baseline") == "kb_bench_mmlongbench_v2"
    assert runner.collection_for(v2, "element_aware") == "kb_bench_mmlongbench_v2_element_aware"


def test_a_manifest_reads_only_its_own_documents(tmp_path):
    documents = tmp_path / "documents"
    documents.mkdir()
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        (documents / name).write_bytes(b"%PDF")
    manifest = _manifest("documents/a.pdf", "documents/c.pdf", "data/train.parquet")

    folder = runner.manifest_documents(tmp_path, manifest, "kb_x")

    assert sorted(p.name for p in folder.iterdir()) == ["a.pdf", "c.pdf"]
    assert (folder / "a.pdf").read_bytes() == b"%PDF"
    # Relative links, so the folder works through a container bind mount.
    assert not (folder / "a.pdf").readlink().is_absolute()
    assert folder.parent == tmp_path / "work" / "kb_x"


async def test_without_generation_every_question_is_an_abstention():
    import json

    class Provider:
        async def chat_json(self, messages, **kwargs):
            raise AssertionError("no model call expected")

    provider = Provider()
    runner.disable_generation(provider)

    raw = json.loads(await provider.chat_json([], model="m"))

    assert raw == {"answer_parts": [], "abstain": True}


def test_a_checkpoint_keeps_finished_questions_for_a_resumed_run(tmp_path):
    # A long run killed midway (memory pressure on a 16 GB Mac) resumes from
    # the questions it already answered instead of starting over.
    checkpoint = tmp_path / "results.partial.jsonl"
    runner.save_checkpoint(checkpoint, {"row_idx": 206, "seconds": 9.1})
    runner.save_checkpoint(checkpoint, {"row_idx": 207, "seconds": 4.5})
    checkpoint.write_text(checkpoint.read_text() + '{"row_idx": 20', encoding="utf-8")

    assert sorted(runner.load_checkpoint(checkpoint)) == [206, 207]
    assert runner.load_checkpoint(tmp_path / "missing.jsonl") == {}
