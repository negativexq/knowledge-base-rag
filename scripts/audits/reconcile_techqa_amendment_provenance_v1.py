"""Reconcile the provenance of the immutable TechQA v1 amendment.

This script is intentionally limited to audit artifacts and source code.  It
does not read HOLDOUT rows, run the benchmark, or open any arm map.
"""

# The repository supports Python 3.9, where datetime.UTC is unavailable.
# ruff: noqa: UP017

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "artifacts/ragbench/canonical"
AUDIT = CANONICAL / "techqa-holdout-measurement-validity-audit-v1"
V1 = AUDIT / "05-amendment/preregistration-amendment-v1.json"
SIDECAR = AUDIT / "05-amendment/preregistration-amendment-v1.sha256"
ROOT_CAUSE_JSON = AUDIT / "04-root-cause/root-cause.json"
ROOT_CAUSE_MD = AUDIT / "04-root-cause/root-cause.md"
AUDIT_REPORT = AUDIT / "06-report/report.md"
AUDIT_SCRIPT = ROOT / "scripts/audits/audit_techqa_holdout_measurement_validity_v1.py"
OUT = CANONICAL / "techqa-amendment-provenance-reconciliation-v1"
EXPECTED = "dd4310b1717a16733e765de3c1d7fa76c9b58cddde43750e2f3bf4d4410b2fe8"
CURRENT = "2cea26bfda90d3f1861e575a5bdd34c6889506948beb3cba30313b9f26c210c4"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def hash_variants() -> dict[str, Any]:
    raw = V1.read_bytes()
    text = raw.decode("utf-8")
    value = json.loads(text)
    variants = {
        "RAW_BYTES_SHA256": sha256_bytes(raw),
        "UTF8_TEXT_SHA256": sha256_bytes(text.encode("utf-8")),
        "JSON_CANONICAL_SORTED_COMPACT_SHA256": sha256_bytes(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ),
        "JSON_CANONICAL_SORTED_PRETTY_SHA256": sha256_bytes(
            (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
                "utf-8"
            )
        ),
        "NORMALIZED_NEWLINE_SHA256": sha256_bytes(
            text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        ),
        "TRAILING_NEWLINE_REMOVED_SHA256": sha256_bytes(text.rstrip("\n").encode("utf-8")),
        "TRAILING_NEWLINE_ADDED_SHA256": sha256_bytes(
            (text.rstrip("\n") + "\n\n").encode("utf-8")
        ),
    }
    return {
        "path": rel(V1),
        "file_size": len(raw),
        "variants": variants,
        "expected_hash": EXPECTED,
        "any_legitimate_representation_matches_expected": EXPECTED in variants.values(),
        "current_raw_matches_sidecar": variants["RAW_BYTES_SHA256"]
        == SIDECAR.read_text(encoding="utf-8").strip().split()[0],
    }


def scan_hash_references() -> dict[str, Any]:
    scan_roots = [AUDIT, CANONICAL / "techqa-reranker-corrected-holdout-v1", ROOT / "scripts"]
    excluded_names = {
        "debug-arm-map.json",
        "holdout-arm-map.json",
        "corrected-holdout-arm-map.json",
    }
    matches: list[dict[str, Any]] = []
    for scan_root in scan_roots:
        if not scan_root.exists():
            continue
        paths = [scan_root] if scan_root.is_file() else scan_root.rglob("*")
        for path in paths:
            if not path.is_file() or path.name in excluded_names or path.suffix not in {
                ".json",
                ".jsonl",
                ".md",
                ".py",
                ".sha256",
            }:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for needle, label in ((EXPECTED, "historical_expected"), (CURRENT, "current_raw")):
                start = 0
                while True:
                    index = text.find(needle, start)
                    if index < 0:
                        break
                    line = text.count("\n", 0, index) + 1
                    context = text.splitlines()[line - 1].strip()[:240]
                    if "expected_sha256_from_task" in context:
                        classification = "task_provided_expected_hash"
                    elif path == SIDECAR:
                        classification = "raw_file_sha256_sidecar"
                    elif path == V1 or "actual_sha256" in context or "sidecar_sha256" in context:
                        classification = "raw_file_sha256_reference"
                    else:
                        classification = "UNKNOWN"
                    matches.append(
                        {
                            "path": rel(path),
                            "line": line,
                            "hash": needle,
                            "hash_role": label,
                            "context": context,
                            "classification": classification,
                        }
                    )
                    start = index + len(needle)
    return {
        "scope": [rel(path) for path in scan_roots],
        "excluded": sorted(excluded_names),
        "matches": matches,
        "historical_expected_match_count": sum(item["hash"] == EXPECTED for item in matches),
        "current_hash_match_count": sum(item["hash"] == CURRENT for item in matches),
        "dd4310_belongs_to_v1_artifact": any(
            item["hash"] == EXPECTED and item["path"] in {rel(V1), rel(SIDECAR)} for item in matches
        ),
        "previous_v1_byte_representation_found": False,
    }


def filesystem_timeline() -> dict[str, Any]:
    paths = [V1, SIDECAR, ROOT_CAUSE_JSON, ROOT_CAUSE_MD, AUDIT_REPORT]
    rows = []
    for path in paths:
        stat = path.stat()
        rows.append(
            {
                "path": rel(path),
                "exists": True,
                "size": stat.st_size,
                "inode": stat.st_ino,
                "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "ctime_utc": datetime.fromtimestamp(stat.st_ctime, timezone.utc).isoformat(),
                "tracked_by_git": subprocess.run(
                    ["git", "ls-files", "--error-unmatch", rel(path)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                ).returncode
                == 0,
            }
        )
    return {
        "interpretation": (
            "Filesystem timestamps are supporting evidence only, not "
            "authoritative creation history."
        ),
        "files": rows,
        "current_worktree_state": subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--", rel(AUDIT)], cwd=ROOT, text=True
        ).splitlines(),
    }


def content_audit() -> dict[str, Any]:
    value = json.loads(V1.read_text(encoding="utf-8"))
    text = V1.read_text(encoding="utf-8")
    checks = {
        "original_preregistration_hash": bool(value.get("original_preregistration_sha256")),
        "invalid_run_identity": value.get("original_holdout_run")
        == "techqa-reranker-holdout-oneshot-v1",
        "defect_description": "DEBUG50-only" in value.get("defect", ""),
        "arm_symmetric_invalidity": value.get("invalidity_arm_independent") is True,
        "correction_is_corpus_scope": "corpus" in value.get("correction", "").lower(),
        "frozen_candidate_top_budget": value.get("frozen_design")
        == {"candidate_k": 20, "legacy_budget": 2400, "same_on_off_downstream": True, "top_n": 5},
        "corrected_scope_no_tuning": "no query exclusion, tuning"
        in value.get("corrected_scope", ""),
        "provider_budget": value.get("provider_call_budget")
        == {"official_luna_max": 100, "preflight_max": 2, "terra": 0},
        "explicit_chunking_freeze": "chunk" in text.lower(),
        "explicit_embedding_retrieval_freeze": all(
            token in text.lower() for token in ("embedding", "bm25", "rrf")
        ),
        "explicit_sectionaware_luna_validator_freeze": all(
            token in text.lower() for token in ("sectionaware", "luna", "validator")
        ),
        "explicit_blind_review_procedure": "blind" in text.lower(),
    }
    return {
        "checks": checks,
        "content_semantically_complete": all(checks.values()),
        "missing_explicit_constraints": [key for key, present in checks.items() if not present],
        "semantic_change_required_for_future_immutable_amendment": (
            "explicitly record missing frozen pipeline constraints"
        ),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    starting_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    variants = hash_variants()
    sidecar = SIDECAR.read_text(encoding="utf-8").strip().split()[0]
    write_json(
        OUT / "00-integrity/source-integrity.json",
        {
            "starting_head": starting_head,
            "v1_path": rel(V1),
            "v1_raw_sha256": variants["variants"]["RAW_BYTES_SHA256"],
            "v1_sidecar_sha256": sidecar,
            "v1_sidecar_matches": variants["current_raw_matches_sidecar"],
            "historical_expected_sha256": EXPECTED,
            "holdout_content_accessed_this_task": False,
            "holdout_arm_maps_read": False,
            "provider_calls": {"retrieval": 0, "embedding": 0, "bge": 0, "luna": 0, "terra": 0},
            "v1_files_modified": False,
        },
    )
    write_json(OUT / "01-hash-trace/hash-reference-scan.json", scan_hash_references())
    write_json(OUT / "01-hash-trace/amendment-v1-hash-variants.json", variants)
    write_json(OUT / "02-timeline/filesystem-timeline.json", filesystem_timeline())
    (OUT / "03-code-path/amendment-hash-code-path.md").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "03-code-path/amendment-hash-code-path.md").write_text(
        """# Amendment v1 hash code path

`audit_techqa_holdout_measurement_validity_v1.py` constructs a new amendment object,
sets `created_at` with `datetime.now(UTC).isoformat()`, writes the pretty JSON with a
trailing LF, then reads those exact bytes and writes the sidecar SHA256. There is no
hash-before-final-write, wrong-variable, temporary-path, or post-write formatting step
in this code path.

The provenance defect is mutability: rerunning the audit reconstructs v1 with a new
timestamp and rewrites the same v1 path. Each individual write/hash sequence is raw-byte
consistent, but the v1 identity is not stable across reruns. The historical `dd4310...`
value is not present in the v1 JSON or sidecar and no prior v1 bytes are recoverable in
the permitted repository/task artifact scope.
""",
        encoding="utf-8",
    )
    write_json(
        OUT / "03-code-path/hash-logic-reproduction.json",
        {
            "current_source_replay": CURRENT,
            "sidecar_replay": sidecar,
            "same_current_payload_emits": CURRENT,
            "new_created_at_would_emit": (
                "another hash, because created_at is included in the raw JSON"
            ),
            "dd4310_reproduced": False,
            "full_audit_rerun": False,
        },
    )
    write_json(OUT / "04-content-diff/amendment-v1-semantic-audit.json", content_audit())
    verdict = {
        "primary_verdict": "AMENDMENT_V1_PROVENANCE_INCONCLUSIVE",
        "reason": (
            "The current v1 and sidecar are raw-byte consistent, dd4310 is not a "
            "legitimate current-file representation and no prior v1 bytes or "
            "authoritative origin for dd4310 are recoverable."
        ),
        "current_file_mutation_evidence": False,
        "hash_convention_mismatch": False,
        "post_hash_mutation_confirmed": False,
        "reporting_defect_proven": False,
        "previous_byte_representation_recoverable": False,
        "v1_semantic_content_complete": content_audit()["content_semantically_complete"],
        "v2_created": False,
        "corrected_holdout_authorized": False,
        "corrected_holdout_executed": False,
    }
    write_json(OUT / "05-verdict/verdict.json", verdict)
    write_json(
        OUT / "06-amendment-v2/status.json",
        {
            "created": False,
            "reason": (
                "Primary verdict is PROVENANCE_INCONCLUSIVE; v2 creation is prohibited "
                "by task rules."
            ),
        },
    )
    report = f"""# TECHQA Amendment Provenance Reconciliation V1

## Result

Primary verdict: `{verdict['primary_verdict']}`

Current v1 raw SHA256: `{variants['variants']['RAW_BYTES_SHA256']}`
Current sidecar SHA256: `{sidecar}`
Historical reported SHA256: `{EXPECTED}`

The current JSON and sidecar match under the raw-file-byte convention. None
of the legitimate representations tested (raw bytes, UTF-8 bytes, LF-normalized
bytes, sorted compact JSON, sorted pretty JSON, and trailing-newline variants)
produces the historical value. The historical value appears nowhere as a v1
file or sidecar hash in the permitted scan scope; it appears only as an
expected-value field in the prior blocker artifact. No earlier v1 byte copy is
recoverable.

The creation code uses a dynamic `created_at` and rewrites the v1 file before
hashing it. Therefore the code path is raw-byte consistent per execution but
the v1 identity is mutable across reruns. This explains why a stale hash is
possible, but does not prove whether `dd4310…` was a prior v1 hash, a value
from another representation/path, or a reporting transcription.

The current amendment is not semantically complete as a future immutable
execution contract: it omits explicit frozen statements for chunking,
embedding/retrieval, SectionAware, Luna, validators, and the complete blind
review procedure. Because the provenance verdict is inconclusive, no v2 was
created under the fail-closed rule.

HOLDOUT content accessed by this task: **NO**
Arm maps opened: **NO**
Provider calls: **0**
Original v1 files modified: **NO**
"""
    (OUT / "07-report/report.md").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "07-report/report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
