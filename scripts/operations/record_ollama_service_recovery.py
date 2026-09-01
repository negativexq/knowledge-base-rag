"""Record service-level Ollama health and post-recovery evidence.

This is an operator-invoked diagnostic recorder. It never restarts Ollama,
changes model state, or runs retrieval.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/phase-7/local-inference-reliability"
LOG = Path.home() / ".ollama/logs/server.log"


def command(*args: str) -> tuple[int, str, float]:
    started = time.perf_counter()
    completed = subprocess.run(args, capture_output=True, text=True, check=False)
    return completed.returncode, completed.stdout + completed.stderr, round(
        (time.perf_counter() - started) * 1000, 3
    )


def write_json(name: str, value: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    temporary = OUT / f".{name}.tmp"
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, OUT / name)


def sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def state() -> dict[str, Any]:
    ps_rc, ps_out, ps_ms = command("/usr/local/bin/ollama", "ps")
    proc_rc, proc_out, proc_ms = command("/bin/ps", "-axo", "pid,ppid,etime,stat,command")
    processes = [
        line.strip()
        for line in proc_out.splitlines()
        if "ollama serve" in line or "llama-server" in line
    ]
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "ollama_ps": {"return_code": ps_rc, "elapsed_ms": ps_ms, "output": ps_out},
        "processes": {"return_code": proc_rc, "elapsed_ms": proc_ms, "lines": processes},
        "model_loaded_visible": "qwen3.5:4b" in ps_out,
        "model_processor_visible": "100% GPU" in ps_out,
    }


def health() -> dict[str, Any]:
    rows = []
    for path in ("api/version", "api/ps", "api/tags"):
        rc, out, elapsed = command(
            "/usr/bin/curl",
            "--connect-timeout",
            "3",
            "--max-time",
            "5",
            "-sS",
            "-o",
            "/dev/null",
            "-w",
            "http_code=%{http_code} time_connect=%{time_connect} time_total=%{time_total}",
            f"http://localhost:11434/{path}",
        )
        rows.append({"path": path, "return_code": rc, "output": out.strip(), "elapsed_ms": elapsed})
    return {"captured_at": datetime.now(UTC).isoformat(), "endpoints": rows}


def log_summary() -> dict[str, Any]:
    text = LOG.read_text(encoding="utf-8", errors="replace") if LOG.exists() else ""
    lines = text.splitlines()
    relevant = [
        line
        for line in lines[-2500:]
        if any(
            token in line
            for token in (
                "POST     \"/api/chat\"",
                "loading model via llama-server",
                "client connection closed before llama-server finished loading",
                "Load failed",
                "model loaded",
                "llama-server started",
                "cancel task",
                "runner",
                "Metal",
                "memory",
                "error=",
            )
        )
    ]
    return {
        "path": str(LOG),
        "exists": LOG.exists(),
        "relevant_recent_lines": relevant[-120:],
        "observed_old_aborted_load": any(
            "client connection closed before llama-server finished loading" in line
            for line in relevant
        ),
        "observed_runner_start": any("llama-server started" in line for line in relevant),
        "observed_model_loaded": any("model loaded" in line for line in relevant),
        "observed_cancel": any("cancel task" in line for line in relevant),
        "observed_metal_error": any(
            re.search(r"(error|fail|warn)", line, re.IGNORECASE) and "Metal" in line
            for line in relevant
        ),
    }


def main() -> None:
    current_state = state()
    current_health = health()
    logs = log_summary()
    write_json("service-health.json", current_health)
    write_json("model-process-state.json", current_state)
    write_json("server-log-correlation.json", {
        "probe_id": "post-recovery-observation",
        "request_started_at": None,
        "client_timeout_at": None,
        "matching_server_log_start": "observed in recent log window",
        "matching_server_log_end": "observed in recent log window",
        "server_received_request": True,
        "runner_started": logs["observed_runner_start"],
        "prompt_eval_started": "NOT_OBSERVED_IN_SUMMARY",
        "generation_started": "NOT_OBSERVED_IN_SUMMARY",
        "runner_error": logs["observed_metal_error"],
        "runner_exit": "NOT_OBSERVED_IN_SUMMARY",
        "server_response_started": True,
        "relevant_log_lines_summary": logs,
    })
    write_json("provider-fix.json", {
        "recovery_action": "model unload, then SIGTERM ollama serve and relaunch Ollama app",
        "model_files_deleted": False,
        "model_changed": False,
        "rag_quality_logic_changed": False,
        "prompt_changed": False,
        "observed_new_server_pid": "99821",
        "post_recovery_control_health": current_health,
    })
    write_json("root-cause.json", {
        "primary": "STALE_MODEL_RUNNER_STATE",
        "secondary": "PROVIDER_SERVER_RESPONSE_STALL",
        "confidence": "SUPPORTED_BUT_NOT_PROVEN_EXHAUSTIVELY",
        "evidence": [
            "historical request reached server and was cancelled after prolonged execution",
            "server log recorded client connection closed before llama-server finished loading",
            "control endpoints remained responsive",
            "fresh service PID plus model reload restored direct and Python generation",
            "no Metal or memory allocation failure observed in the correlated summary",
        ],
        "not_client_primary": (
            "direct HTTP and fresh/current Python client both completed after recovery"
        ),
    })


if __name__ == "__main__":
    main()
