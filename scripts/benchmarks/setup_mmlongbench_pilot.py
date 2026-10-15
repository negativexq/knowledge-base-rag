"""Download the MMLongBench-Doc pilot files pinned in
artifacts/mmlongbench-pilot/manifest.json into the gitignored data/ folder.

Every file is checked against the manifest's size and git blob id (the
Hub's own listing) before it is written; files already present and
matching are not fetched again. Nothing lands in the repository.
"""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.evaluation.mmlongbench import download_manifest_files, load_manifest

MANIFEST = ROOT / "artifacts" / "mmlongbench-pilot" / "manifest.json"
DATA_DIR = ROOT / "data" / "benchmarks" / "mmlongbench-doc"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - pinned https URL
        return response.read()


def data_dir(manifest_revision: str) -> Path:
    return DATA_DIR / manifest_revision


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    for path in download_manifest_files(manifest, data_dir(manifest.revision), fetch):
        print(f"verified {path.relative_to(ROOT)} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
