"""Single-source chunking configuration.

The legacy chunker calls its word window a ``token`` window.  It remains
available as the Sprint 27 baseline so historical retrieval results stay
reproducible.  Token-aware configurations use the tokenizer named here and
carry their exact settings into the pipeline fingerprint.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

QWEN3_EMBEDDING_TOKENIZER = "Qwen/Qwen3-Embedding-4B"
QWEN3_TOKENIZER_REVISION = "main"
BOUNDARY_STRATEGY = "sentence_heading_page_v1"


@dataclass(frozen=True)
class ChunkingConfig:
    name: str
    mode: str
    target_tokens: int
    overlap_tokens: int
    hard_max_tokens: int | None
    tokenizer_model: str
    tokenizer_revision: str
    boundary_strategy: str

    def __post_init__(self) -> None:
        if self.target_tokens <= 0:
            raise ValueError("target_tokens must be greater than zero")
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than target_tokens")
        if self.hard_max_tokens is not None and self.hard_max_tokens < self.target_tokens:
            raise ValueError("hard_max_tokens must be at least target_tokens")
        if self.mode not in {"baseline", "token_aware"}:
            raise ValueError(f"unsupported chunking mode: {self.mode!r}")

    @property
    def token_aware(self) -> bool:
        return self.mode == "token_aware"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def current_baseline(cls) -> ChunkingConfig:
        return cls(
            name="baseline",
            mode="baseline",
            target_tokens=500,
            overlap_tokens=50,
            hard_max_tokens=None,
            tokenizer_model=QWEN3_EMBEDDING_TOKENIZER,
            tokenizer_revision=QWEN3_TOKENIZER_REVISION,
            boundary_strategy="legacy_word_sentence_heading_page_v1",
        )

    @classmethod
    def token_aware_candidate(cls, target_tokens: int, overlap_tokens: int) -> ChunkingConfig:
        # Pre-committed before the benchmark: a bounded +64-token allowance
        # permits a sentence to finish while still giving every candidate a
        # deterministic hard ceiling.  The final chunk may be shorter.
        return cls(
            name=f"{target_tokens}-{overlap_tokens}",
            mode="token_aware",
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
            hard_max_tokens=target_tokens + 64,
            tokenizer_model=QWEN3_EMBEDDING_TOKENIZER,
            tokenizer_revision=QWEN3_TOKENIZER_REVISION,
            boundary_strategy=BOUNDARY_STRATEGY,
        )


PRIMARY_CANDIDATES = (
    ChunkingConfig.token_aware_candidate(256, 32),
    ChunkingConfig.token_aware_candidate(384, 48),
    ChunkingConfig.token_aware_candidate(512, 64),
    ChunkingConfig.token_aware_candidate(768, 96),
)


def config_for_name(name: str) -> ChunkingConfig:
    if name == "baseline":
        return ChunkingConfig.current_baseline()
    for config in PRIMARY_CANDIDATES:
        if config.name == name:
            return config
    raise ValueError(f"unknown chunking config {name!r}")
