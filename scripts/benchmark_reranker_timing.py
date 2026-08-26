"""Sprint 27 controlled reranker timing and candidate-input equivalence.

This is deliberately separate from retrieval quality benchmarking.  One
CrossEncoder is loaded once, warmup is completed, every measured call uses
the same 20 candidate texts and the same predict() boundary, and config
labels are only balanced labels over repeated calls.  It therefore answers
whether the earlier per-config timing gap was a chunking effect or runtime
noise without mutating Qdrant.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app.evaluation.reranker_timing import (
    balanced_config_order,
    candidate_text_fingerprint,
    summarize_latencies,
)
from app.ingestion.chunker import chunk_document
from app.ingestion.chunking_config import config_for_name
from app.ingestion.markdown_chunker import chunk_markdown_document
from app.ingestion.tokenizer import token_count
from app.reranker.cross_encoder import CrossEncoderReranker
from app.shared.config import settings
from app.shared.slug import slugify
from scripts.benchmark_embeddings import build_corpus

CONFIGS = ("baseline", "256-32", "384-48", "512-64", "768-96")
QUERY = "Which header must Nimbus API requests include, and how long does the token stay valid?"
REPETITIONS = 5
SEED = 2701
CANDIDATE_COUNT = 20


def reconstructed_candidate_texts(work_dir: Path, config_name: str) -> list[str]:
    docs_dir = work_dir / "corpus"
    config = config_for_name(config_name)
    chunks = []
    for path in sorted(docs_dir.iterdir()):
        source_id = slugify(path.name)
        if path.suffix == ".pdf":
            chunks.extend(
                chunk_document(str(path), source_id, "filesystem", chunking_config=config)
            )
        elif path.suffix == ".md":
            chunks.extend(
                chunk_markdown_document(str(path), source_id, "filesystem", chunking_config=config)
            )
    ordered = sorted(chunks, key=lambda chunk: (chunk.source_id, chunk.char_range, chunk.text))
    return [chunk.text for chunk in ordered[:CANDIDATE_COUNT]]


def run(work_dir: Path, repetitions: int = REPETITIONS) -> dict:
    work_dir.mkdir(parents=True, exist_ok=True)
    build_corpus(work_dir / "corpus")
    input_fingerprints = {}
    candidate_texts_by_config = {}
    for config_name in CONFIGS:
        texts = reconstructed_candidate_texts(work_dir, config_name)
        candidate_texts_by_config[config_name] = texts
        config = config_for_name(config_name)
        input_fingerprints[config_name] = candidate_text_fingerprint(
            QUERY,
            texts,
            [
                token_count(text, config.tokenizer_model, config.tokenizer_revision)
                for text in texts
            ],
        )

    canonical_texts = candidate_texts_by_config["512-64"]
    canonical_config = config_for_name("512-64")
    canonical_fingerprint = candidate_text_fingerprint(
        QUERY,
        canonical_texts,
        [
            token_count(text, canonical_config.tokenizer_model, canonical_config.tokenizer_revision)
            for text in canonical_texts
        ],
    )
    equivalent = {
        config_name: input_fingerprints[config_name]["sha256"] == canonical_fingerprint["sha256"]
        for config_name in CONFIGS
    }

    device = "cpu"
    reranker = CrossEncoderReranker(
        settings.reranker_model,
        trust_remote_code=settings.reranker_trust_remote_code,
        device=device,
    )
    pairs = [[QUERY, text] for text in canonical_texts]
    # Warmup is outside the timing boundary and uses the exact same input.
    for _ in range(2):
        reranker._model.predict(pairs, batch_size=20, show_progress_bar=False)

    order = balanced_config_order(CONFIGS, repetitions, SEED)
    measured: dict[str, list[float]] = {config_name: [] for config_name in CONFIGS}
    order_log = []
    for index, config_name in enumerate(order):
        started = time.perf_counter()
        reranker._model.predict(pairs, batch_size=20, show_progress_bar=False)
        elapsed_ms = (time.perf_counter() - started) * 1000
        measured[config_name].append(elapsed_ms)
        order_log.append(
            {"position": index, "config": config_name, "duration_ms": round(elapsed_ms, 3)}
        )

    return {
        "method": {
            "model": settings.reranker_model,
            "backend": settings.reranker_backend,
            "device": device,
            "candidate_count": CANDIDATE_COUNT,
            "batch_size": CANDIDATE_COUNT,
            "model_loads": 1,
            "warmup_calls": 2,
            "repetitions_per_config": repetitions,
            "seed": SEED,
            "timed_boundary": "CrossEncoder.predict only",
            "unmeasured": ["Qdrant", "embedding", "retrieval", "indexing", "generation"],
        },
        "query": "fixture query id: api-auth-en-native",
        "candidate_input": {
            "equivalent_across_configs": equivalent,
            "canonical": canonical_fingerprint,
            "per_config": input_fingerprints,
        },
        "latency_ms": {
            config_name: summarize_latencies(values) for config_name, values in measured.items()
        },
        "order": order_log,
        "interpretation": (
            "All config labels were measured with the same candidate input; any residual "
            "difference is runtime variance, not a demonstrated chunking-cost causal effect."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--work-dir", default="artifacts/chunking-benchmark-sprint27/timing-work"
    )
    parser.add_argument(
        "--output", default="artifacts/chunking-benchmark-sprint27/reranker-latency.json"
    )
    parser.add_argument("--repetitions", type=int, default=REPETITIONS)
    args = parser.parse_args()
    started = time.perf_counter()
    result = run(Path(args.work_dir), repetitions=args.repetitions)
    result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result["latency_ms"], indent=2))


if __name__ == "__main__":
    main()
