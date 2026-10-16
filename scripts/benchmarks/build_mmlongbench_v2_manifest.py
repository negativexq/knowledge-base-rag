"""Write artifacts/mmlongbench-v2/manifest.json: the focused MMLongBench-Doc
set for chunking and evidence-assembly experiments.

The five pilot PDFs plus eight more chosen for structure a chunker has to
keep (10-K tables, guidebooks, slide reports, an administration file).
Questions: every one whose evidence includes text, a table or layout text,
plus at most two unanswerable questions per document. Files are pinned by
the Hub's tree listing at the dataset revision: git blob id for files in
git, sha256 for LFS files.
"""

# ruff: noqa: E402

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pyarrow.parquet as pq

from app.evaluation.mmlongbench import load_manifest, select_focused_rows

PILOT_MANIFEST = ROOT / "artifacts" / "mmlongbench-pilot" / "manifest.json"
OUT = ROOT / "artifacts" / "mmlongbench-v2" / "manifest.json"
DATA_DIR = ROOT / "data" / "benchmarks" / "mmlongbench-doc"
UNANSWERABLE_PER_DOC = 2
ADDED_DOCS = (
    "BESTBUY_2023_10K.pdf",
    "COSTCO_2021_10K.pdf",
    "germanwingsdigitalcrisisanalysis-150403064828-conversion-gate01_95.pdf",
    "8dfc21ec151fb9d3578fc32d5c4e5df9.pdf",
    "User_Manual_1500S_Classic_EN.pdf",
    "05-03-18-political-release.pdf",
    "measuringsuccessonfacebooktwitterlinkedin-160317142140_95.pdf",
    "f8d3a162ab9507e021d83dd109118b60.pdf",
)


def hub_tree(dataset: str, revision: str) -> dict[str, dict]:
    url = f"https://huggingface.co/api/datasets/{dataset}/tree/{revision}/documents"
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - pinned https URL
        return {entry["path"]: entry for entry in json.loads(response.read())}


def pinned(entry: dict) -> dict:
    if entry.get("lfs"):
        return {"path": entry["path"], "size": entry["size"], "sha256": entry["lfs"]["oid"]}
    return {"path": entry["path"], "size": entry["size"], "git_oid": entry["oid"]}


def main() -> None:
    pilot = load_manifest(PILOT_MANIFEST)
    pilot_raw = json.loads(PILOT_MANIFEST.read_text(encoding="utf-8"))
    tree = hub_tree(pilot.dataset, pilot.revision)
    pilot_docs = [f["path"] for f in pilot_raw["files"] if f["path"].startswith("documents/")]
    added = [f"documents/{name}" for name in ADDED_DOCS]
    files = [f for f in pilot_raw["files"] if f["path"] in pilot_docs]
    files += [pinned(tree[path]) for path in added]
    files += [f for f in pilot_raw["files"] if f["path"].startswith("data/")]

    table = pq.read_table(
        DATA_DIR / pilot.revision / "data" / "train-00000-of-00001.parquet"
    ).to_pylist()
    doc_ids = [Path(path).name for path in pilot_docs + added]
    rows = select_focused_rows(table, doc_ids, unanswerable_per_doc=UNANSWERABLE_PER_DOC)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "dataset": pilot.dataset,
        "revision": pilot.revision,
        "selection": (
            f"{len(doc_ids)} PDFs (the 5 pilot PDFs plus 10-Ks, guidebooks, slide reports and "
            "an administration file); every question whose evidence includes text, a table "
            f"or layout text, plus the first {UNANSWERABLE_PER_DOC} unanswerable questions "
            "per PDF, in row order."
        ),
        "files": files,
        "question_rows": rows,
    }
    OUT.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(files)} files, {len(rows)} questions")


if __name__ == "__main__":
    main()
