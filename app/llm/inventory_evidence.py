"""Native observations flag concrete contradictions; layout hints are not release gates."""

from __future__ import annotations

import re
from typing import Any

from app.evidence.support_units import SupportUnit
from app.llm.quantity_state import QuantityCatalogPage, QuantityDraft, QuantityIssue, QuantitySource


def extend_inventory_window(
    selection: QuantitySource, units: dict[str, SupportUnit]
) -> QuantitySource:
    """Peek forward within admitted authority; never enlarge the three-page ceiling."""
    if (
        selection.operation_kind != "count"
        or not 1 <= len(selection.pages) < 3
        or selection.pages != list(range(selection.pages[0], selection.pages[-1] + 1))
    ):
        return selection
    first = units[selection.support_ids[0]]
    ids, pages = list(selection.support_ids), list(selection.pages)
    for page in range(pages[-1] + 1, pages[-1] + 1 + (3 - len(pages))):
        candidates = [
            u
            for u in units.values()
            if u.authorized
            and u.model_visible
            and (u.source_id, u.document_version) == (first.source_id, first.document_version)
            and (u.page_number or 1) <= page <= (u.page_end or u.page_number or 1)
        ]
        if not candidates:
            break
        candidates.sort(
            key=lambda u: ((u.page_end or u.page_number or 1) - (u.page_number or 1), len(u.text))
        )
        key = next((key for key in ids if any(u.support_unit_id == key for u in candidates)), None)
        key = key or candidates[0].support_unit_id
        if key not in ids:
            if len(ids) == 3:
                break
            ids.append(key)
        pages.append(page)
    return selection.model_copy(update={"support_ids": ids, "pages": pages})


def numbered_window_hints(
    catalog: list[QuantityCatalogPage], question: str
) -> list[dict[str, Any]]:
    """Offer bounded source windows covering literal IDs; never certify question scope."""
    words = re.findall(r"[a-z]+", question.casefold())
    groups: dict[tuple[str, str, str], list[tuple[QuantityCatalogPage, set[str]]]] = {}
    for page in catalog:
        families: dict[str, set[str]] = {}
        for label in page.numbered_items:
            match = re.fullmatch(r"([A-Za-z][A-Za-z-]*)\s*#\s*(\d+)", label)
            if not match:
                continue
            family = match[1].casefold()
            if not any(word.startswith(family[:4]) for word in words):
                continue
            families.setdefault(family, set()).add(family + " #" + match[2])
        for family, labels in families.items():
            groups.setdefault((page.source_id, page.document_version, family), []).append(
                (page, labels)
            )
    hints = []
    for (source, version, family), choices in groups.items():
        chosen: list[QuantityCatalogPage] = []
        covered: set[str] = set()
        for _ in range(3):
            available = [(p, labels) for p, labels in choices if p not in chosen]
            if not available:
                break
            page, labels = max(
                available, key=lambda pair: (len(pair[1] - covered), -pair[0].physical_page)
            )
            if not labels - covered:
                break
            chosen.append(page)
            covered.update(labels)
        hints.append(
            {
                "source_id": source,
                "document_version": version,
                "label_family": family,
                "physical_pages": sorted(p.physical_page for p in chosen),
                "support_ids": list(dict.fromkeys(p.support_ids[0] for p in chosen)),
                "observed_identifiers": sorted(covered),
                "authority": "Location hint only; may cover more than the requested subset. "
                "Inspect original pages and the actual question; not a completeness receipt.",
            }
        )
    return hints[:3]


def prefer_document_inventory_window(
    selection: QuantitySource,
    catalog: list[QuantityCatalogPage],
    question: str,
    units: dict[str, SupportUnit],
) -> QuantitySource:
    """Improve a declared document inventory's location, not its answer or coverage verdict."""
    if (
        selection.operation_kind != "count"
        or selection.inventory_scope != "document"
        or not selection.support_ids
    ):
        return selection
    source = units[selection.support_ids[0]]
    hints = [
        h
        for h in numbered_window_hints(catalog, question)
        if (h["source_id"], h["document_version"]) == (source.source_id, source.document_version)
    ]
    if len(hints) != 1:
        return selection
    hint = hints[0]
    old = {
        re.sub(r"\s*#\s*", " #", label.casefold())
        for page in catalog
        if page.physical_page in selection.pages
        and (page.source_id, page.document_version) == (source.source_id, source.document_version)
        for label in page.numbered_items
        if label.casefold().startswith(hint["label_family"])
    }
    if not old < set(hint["observed_identifiers"]):
        return selection
    ids = hint["support_ids"]
    if any(
        key not in units
        or not units[key].authorized
        or not units[key].model_visible
        or (units[key].source_id, units[key].document_version)
        != (source.source_id, source.document_version)
        for key in ids
    ):
        return selection
    if any(
        not any(
            (units[key].page_number or 1)
            <= page
            <= (units[key].page_end or units[key].page_number or 1)
            for key in ids
        )
        for page in hint["physical_pages"]
    ):
        return selection
    return selection.model_copy(
        update={
            "support_ids": ids,
            "pages": hint["physical_pages"],
            "modality": "image",
        }
    )


def inventory_model_view(context: dict[str, Any]) -> dict[str, Any]:
    """Keep every native line; send geometry only for structural location hints."""
    if not context:
        return {}
    return {
        **context,
        "pages": [
            {
                **page,
                "lines": [
                    {
                        "id": line["id"],
                        "text": line["text"],
                        **({"heading": True} if line["heading"] else {}),
                        **({"caption": True} if line["caption"] else {}),
                        **(
                            {"bbox": line["bbox"], "size": line["size"]}
                            if line["heading"] or line["caption"]
                            else {}
                        ),
                    }
                    for line in page["lines"]
                ],
            }
            for page in context["pages"]
        ],
    }


def _text(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def inventory_issues(
    draft: QuantityDraft, context: dict[str, Any], question: str
) -> list[QuantityIssue]:
    if draft.mode != "count" or not context:
        return []
    pages = context["pages"]
    lines = [
        {**line, "page": page["page"]}
        for page in sorted(pages, key=lambda p: p["page"])
        for line in page["lines"]
    ]
    by_id = {line["id"]: i for i, line in enumerate(lines)}
    issues = []
    for index, group in enumerate(draft.groups):

        def fail(kind: str, detail: str, anchor: dict[str, Any] | None = None) -> None:
            line = anchor or (lines[0] if lines else None)
            issues.append(
                QuantityIssue(
                    target="group",
                    index=index,
                    kind="boundary" if kind == "coverage" else "wrong_binding",
                    page=line["page"] if line else pages[0]["page"],
                    witness=line["text"] if line else "Native context is incomplete",
                    description=detail,
                    needed_evidence="Source-grounded object membership and inventory closure",
                )
            )

        start = by_id.get(group.object_anchor)
        # Native extraction may miss a heading or flatten a table. Missing
        # layout metadata is not counterevidence to an independently checked image.
        if start is None:
            continue
        anchor = lines[start]
        spatial = re.search(
            r"\b(?:at|on|near)\s+(?:the\s+)?(bottom|top)\b|"
            r"\b(bottom|top)(?:most)?\s+(?:figure|table)\b",
            question,
            re.I,
        )
        if spatial and anchor["caption"]:
            caption_prefix = re.match(r"[A-Za-z]+", anchor["text"])
            peers = [
                entry
                for entry in lines
                if entry["page"] == anchor["page"]
                and entry["caption"]
                and caption_prefix
                and entry["text"].casefold().startswith(caption_prefix[0].casefold())
            ]
            expected = (max if "bottom" in spatial[0].casefold() else min)(
                peers, key=lambda entry: entry["bbox"][1]
            )
            if expected["id"] != anchor["id"]:
                fail(
                    "binding",
                    "INVENTORY_OBJECT_LOCATION_MISMATCH: selected caption is outside "
                    "the requested location",
                    anchor,
                )
        end = by_id.get(group.closure_anchor)
        # Closure is judged from the actual source by the checker. A parser
        # heading ID is an optional locator, not a mandatory proof format.
        end = end if end is not None and end >= start else len(lines)
        # Typography is used only for clear counterevidence in the same native
        # page/reading order, not to infer semantic inventories from all bold text.
        peer = next(
            (
                i
                for i in range(start + 1, len(lines))
                if lines[i]["page"] == anchor["page"]
                and lines[i]["heading"]
                and re.search(r"[A-Za-z]", lines[i]["text"])
                and _text(lines[i]["text"]) not in {_text(item.text) for item in group.items}
                and lines[i]["size"] >= anchor["size"] - 0.2
                and abs(lines[i]["bbox"][0] - anchor["bbox"][0]) < 0.03
            ),
            None,
        )
        member_end = min(end, peer) if peer is not None and not anchor["caption"] else end
        body = _text(" ".join(entry["text"] for entry in lines[start:member_end]))
        if not anchor["caption"] and (
            group.closure_basis == "bounded_object" or _text(anchor["text"]) in _text(group.label)
        ):
            for item in group.items:
                value = _text(item.text)
                # A short number/substring can occur anywhere in a PDF and
                # cannot establish ownership. Only exact textual labels outside
                # an observed sibling boundary constitute this counterexample.
                outside = [entry for entry in lines[member_end:] if _text(entry["text"]) == value]
                if (
                    peer is not None
                    and value
                    and any(ch.isalpha() for ch in value)
                    and outside
                    and value not in body
                ):
                    fail("binding", f"INVENTORY_MEMBER_OUTSIDE_OBJECT: {item.text[:150]}", anchor)
                    break
        # A source-declared comprehensive inventory is still checked for omitted
        # explicit item identifiers throughout the observed source window.
        scope_text = " ".join(
            entry["text"]
            for entry in (
                lines if group.closure_basis == "declared_inventory" else lines[start:end]
            )
        )
        pattern = r"([A-Za-z][A-Za-z ]{0,40}?)\s*#\s*(\d+)"
        observed = {
            (m[0].strip().casefold(), m[1])
            for item in group.items
            for m in re.findall(pattern, item.text)
        }
        for prefix in {prefix for prefix, _ in observed}:
            found = set(re.findall(re.escape(prefix) + r"\s*#\s*(\d+)", scope_text, re.I))
            missing = found - {n for p, n in observed if p == prefix}
            if missing:
                fail(
                    "coverage",
                    "INVENTORY_SOURCE_ITEMS_OMITTED: "
                    + prefix
                    + " #"
                    + ", #".join(sorted(missing)),
                    anchor,
                )
    return issues
