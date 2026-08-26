import pytest

from app.ingestion.chunker import chunk_document
from app.ingestion.chunking_config import PRIMARY_CANDIDATES, ChunkingConfig
from app.ingestion.fingerprint import build_pipeline_fingerprint
from app.ingestion.markdown_chunker import chunk_markdown_text
from app.ingestion.tokenizer import token_count
from app.llm.embedding_models import qwen3_4b_config
from app.shared.config import Settings


def _config(target: int = 256, overlap: int = 32) -> ChunkingConfig:
    return ChunkingConfig.token_aware_candidate(target, overlap)


@pytest.mark.parametrize("config", PRIMARY_CANDIDATES, ids=lambda item: item.name)
def test_primary_candidate_matrix_has_precommitted_bounds(config):
    assert config.mode == "token_aware"
    assert config.overlap_tokens < config.target_tokens
    assert config.hard_max_tokens == config.target_tokens + 64


def test_token_count_is_from_the_configured_qwen_tokenizer_and_is_carried_on_chunks():
    text = "# Türkçe başlık\n\n" + "Merhaba dünya; güvenli içerik ve citation bilgisi. " * 80
    chunks = chunk_markdown_text(
        text,
        source_id="doc",
        source_type="markdown",
        doc_id="hash",
        chunking_config=_config(),
    )

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count == token_count(
            chunk.text, _config().tokenizer_model, _config().tokenizer_revision
        )
        assert chunk.token_count <= _config().hard_max_tokens


def test_token_aware_output_is_deterministic_and_uses_real_token_overlap():
    text = "# Bölüm\n\n" + "Sentence with enough Turkish karakterleri. " * 100
    first = chunk_markdown_text(text, "doc", "markdown", "hash", chunking_config=_config())
    second = chunk_markdown_text(text, "doc", "markdown", "hash", chunking_config=_config())

    assert first == second
    assert all(chunk.overlap_token_count == 32 for chunk in first[1:])


def test_markdown_heading_and_code_block_are_kept_in_their_heading_section():
    text = (
        "# Deploy\n\n"
        "The deployment answer stays under this heading.\n\n"
        "```bash\n"
        "kubectl apply -f deployment.yaml\n"
        "kubectl rollout status deployment/api\n"
        "```\n"
    )
    chunks = chunk_markdown_text(text, "doc", "markdown", "hash", chunking_config=_config(32, 4))

    assert chunks
    assert all(chunk.heading_path == ("Deploy",) for chunk in chunks)
    assert any(
        "kubectl apply" in chunk.text and "kubectl rollout" in chunk.text for chunk in chunks
    )
    assert all(chunk.heading_preserved is True for chunk in chunks)


def test_pdf_token_aware_chunks_do_not_cross_page_boundaries(sample_pdf):
    chunks = chunk_document(
        sample_pdf,
        source_id="sample",
        chunk_size_tokens=256,
        overlap_tokens=32,
        chunking_config=_config(),
    )

    assert chunks
    assert all(chunk.page_crossing is False for chunk in chunks)
    assert all(chunk.token_count <= 320 for chunk in chunks)
    assert all(f"PAGE{chunk.page_number}-" in chunk.text for chunk in chunks)


def test_chunk_config_dimensions_change_pipeline_fingerprint():
    embedding = qwen3_4b_config(Settings())
    small = build_pipeline_fingerprint(embedding, _config(256, 32))
    large = build_pipeline_fingerprint(embedding, _config(512, 64))
    tokenizer_changed = build_pipeline_fingerprint(
        embedding,
        ChunkingConfig(
            name="other-tokenizer",
            mode="token_aware",
            target_tokens=256,
            overlap_tokens=32,
            hard_max_tokens=320,
            tokenizer_model="other/tokenizer",
            tokenizer_revision="rev-2",
            boundary_strategy="sentence_heading_page_v1",
        ),
    )

    assert small.digest() != large.digest()
    assert small.digest() != tokenizer_changed.digest()
