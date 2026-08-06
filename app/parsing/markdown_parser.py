import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_FENCE_RE = re.compile(r"^\s*```")


@dataclass(frozen=True)
class MarkdownBlock:
    heading_path: tuple[str, ...]
    block_index: int
    text: str


def extract_blocks(markdown_text: str) -> list[MarkdownBlock]:
    """Split markdown into text blocks (paragraphs, separated by blank
    lines), each tagged with the heading path (H1 > H2 > ...) it falls
    under — the markdown analogue of a PDF page's per-page paragraphs.

    block_index restarts at 0 for each new heading_path, mirroring a PDF
    page's per-page paragraph_index. A heading jump that skips a level
    (e.g. H1 straight to H3) is treated as a child of the nearest shallower
    heading — a deliberate simplification, not a full outline validator.

    A fenced code block (```` ``` ````) is kept as a single block — its
    internal blank lines don't fragment it into unrelated paragraphs.
    """
    heading_stack: list[str] = []
    blocks: list[MarkdownBlock] = []
    block_counts: dict[tuple[str, ...], int] = {}
    current_lines: list[str] = []
    in_code_fence = False

    def flush() -> None:
        nonlocal current_lines
        text = "\n".join(current_lines).strip()
        current_lines = []
        if not text:
            return
        heading_path = tuple(heading_stack)
        block_index = block_counts.get(heading_path, 0)
        block_counts[heading_path] = block_index + 1
        blocks.append(MarkdownBlock(heading_path=heading_path, block_index=block_index, text=text))

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
            continue

        if line.strip() == "":
            flush()
        else:
            current_lines.append(line)

    flush()
    return blocks
