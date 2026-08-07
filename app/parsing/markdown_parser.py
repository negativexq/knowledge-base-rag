import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_FENCE_RE = re.compile(r"^\s*```")


@dataclass(frozen=True)
class MarkdownBlock:
    heading_path: tuple[str, ...]
    # Sprint 17.5: which occurrence of this exact heading_path this block
    # belongs to (0-indexed, first-seen order). A heading_path alone isn't
    # a unique section identity — the same path (e.g. two separate "#
    # Overview" sections in one document) can legitimately recur, and
    # without this, blocks from both occurrences were indistinguishable
    # from continuous content of a single section. See
    # docs/sprint-17-5-plan.md.
    heading_occurrence: int
    block_index: int
    text: str


def extract_blocks(markdown_text: str) -> list[MarkdownBlock]:
    """Split markdown into text blocks (paragraphs, separated by blank
    lines), each tagged with the heading path (H1 > H2 > ...) it falls
    under — the markdown analogue of a PDF page's per-page paragraphs.

    block_index restarts at 0 for each new (heading_path, heading_occurrence)
    pair, mirroring a PDF page's per-page paragraph_index. A heading jump
    that skips a level (e.g. H1 straight to H3) is treated as a child of
    the nearest shallower heading — a deliberate simplification, not a
    full outline validator.

    A fenced code block (```` ``` ````) is kept as a single block — its
    internal blank lines don't fragment it into unrelated paragraphs.
    """
    heading_stack: list[str] = []
    blocks: list[MarkdownBlock] = []
    block_counts: dict[tuple[tuple[str, ...], int], int] = {}
    occurrence_by_path: dict[tuple[str, ...], int] = {}
    current_occurrence = 0
    current_lines: list[str] = []
    in_code_fence = False

    def flush() -> None:
        nonlocal current_lines
        text = "\n".join(current_lines).strip()
        current_lines = []
        if not text:
            return
        heading_path = tuple(heading_stack)
        key = (heading_path, current_occurrence)
        block_index = block_counts.get(key, 0)
        block_counts[key] = block_index + 1
        blocks.append(
            MarkdownBlock(
                heading_path=heading_path,
                heading_occurrence=current_occurrence,
                block_index=block_index,
                text=text,
            )
        )

    for line in markdown_text.splitlines():
        if _FENCE_RE.match(line):
            current_lines.append(line)
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            current_lines.append(line)
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            flush()
            level = len(heading_match.group(1))
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(heading_match.group(2))
            heading_path = tuple(heading_stack)
            current_occurrence = occurrence_by_path.get(heading_path, 0)
            occurrence_by_path[heading_path] = current_occurrence + 1
            continue

        if line.strip() == "":
            flush()
        else:
            current_lines.append(line)

    flush()
    return blocks
