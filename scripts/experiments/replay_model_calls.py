"""Replay recorded adaptive model calls at another reasoning effort.

Reads raw-text forensic captures (run_adaptive_trace.py writes them) whose
stages keep each call's exact input. The same instructions, prompt, images
and output schema are sent again with only the reasoning effort changed, and
the verdict fields are compared with the recorded output. Replaying the
recorded effort too gives the run-to-run agreement to compare against.
Paid: every replayed call is a model request.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pydantic_ai import Agent, BinaryContent, StructuredDict, ToolOutput  # noqa: E402

from app.llm.agentic import agent_model  # noqa: E402
from app.shared.config import Settings  # noqa: E402


def output_object(raw: str) -> dict[str, Any] | None:
    """The recorded raw_model_output is a JSON list of tool-call argument strings."""
    try:
        parts = json.loads(raw)
        return json.loads(parts[-1]) if isinstance(parts[-1], str) else parts[-1]
    except (ValueError, IndexError, TypeError):
        return None


def verdict(role: str, output: dict[str, Any] | None) -> dict[str, Any] | None:
    """The fields the application acts on, without free-text reasons or witnesses."""
    if output is None:
        return None
    disposition = output.get("source_disposition") or {}
    proposal = disposition.get("proposal", disposition) if isinstance(disposition, dict) else {}
    if role == "scope_validator":
        return {
            "checks": [c.get("verdict") for c in output.get("checks", [])],
            "requirements": [r.get("verdict") for r in output.get("requirement_bindings", [])],
            "objections": len(output.get("objections", [])),
            "omissions": len(output.get("material_omissions", [])),
            "disposition": proposal.get("kind") if proposal else None,
        }
    return {
        "inputs": output.get("inputs"),
        "coverage": output.get("coverage"),
        "operation": output.get("operation"),
        "issues": sorted(i.get("kind", "") for i in output.get("issues", [])),
        "alternatives": sorted(output.get("alternatives", [])),
        "disposition": proposal.get("kind") if proposal else None,
    }


def passes(role: str, summary: dict[str, Any] | None) -> bool | None:
    """Whether the judgment would let the answer or input through."""
    if summary is None:
        return None
    if role == "scope_validator":
        return (
            all(v == "supported" for v in summary["checks"] + summary["requirements"])
            and not summary["objections"]
            and not summary["omissions"]
        )
    return (
        summary["inputs"] == "supported"
        and summary["coverage"] == "complete"
        and summary["operation"] == "supported"
        and not summary["issues"]
    )


def recorded_calls(directories: list[Path], roles: set[str]) -> list[dict[str, Any]]:
    calls = []
    for directory in directories:
        for path in sorted(directory.glob("**/03-captures/records/*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            for name, stage in record.get("stages", {}).items():
                if stage.get("role") in roles and isinstance(stage.get("raw_model_input"), dict):
                    calls.append({"run": str(directory), "stage": name, **stage})
    return calls


async def replay(model, call: dict[str, Any], effort: str) -> dict[str, Any]:
    recorded = call["raw_model_input"]
    agent = Agent(
        model,
        output_type=ToolOutput(StructuredDict(recorded["output_schema"]), strict=True),
        instructions=recorded["instructions"],
        retries=0,
    )
    prompt: Any = recorded["prompt_text"]
    images = [base64.b64decode(i) for i in recorded["images_png_base64"]]
    if images:
        prompt = [recorded["prompt_text"]]
        bindings = json.loads(recorded["prompt_text"]).get("source_images", [])
        for index, blob in enumerate(images):
            if len(bindings) == len(images):
                prompt.append(json.dumps({"source_image": bindings[index]}, ensure_ascii=False))
            prompt.append(BinaryContent(data=blob, media_type="image/png"))
    settings = {**recorded["model_settings"], "openai_reasoning_effort": effort}
    started = time.monotonic()
    try:
        result = await agent.run(prompt, model_settings=settings)
    except Exception as exc:  # a failed replay is a result, not a crash
        return {
            "effort": effort,
            "error": type(exc).__name__,
            "seconds": time.monotonic() - started,
        }
    usage = result.usage()
    return {
        "effort": effort,
        "seconds": round(time.monotonic() - started, 2),
        "output": result.output,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }


async def main(args: argparse.Namespace) -> None:
    roles = set(args.roles.split(","))
    calls = recorded_calls([Path(d) for d in args.captures], roles)
    print(f"{len(calls)} recorded calls", flush=True)
    settings = Settings(generation_provider="openai", openai_model=args.model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    async with agent_model(settings) as model:
        with args.out.open("a", encoding="utf-8") as out:
            for call in calls:
                recorded = verdict(call["role"], output_object(call["raw_model_output"]))
                line = {
                    "run": call["run"],
                    "stage": call["stage"],
                    "role": call["role"],
                    "recorded_effort": call["raw_model_input"]["model_settings"].get(
                        "openai_reasoning_effort"
                    ),
                    "recorded": recorded,
                    "recorded_passes": passes(call["role"], recorded),
                    "replays": [],
                }
                for effort in args.efforts.split(","):
                    result = await replay(model, call, effort)
                    summary = verdict(call["role"], result.get("output"))
                    result.update(
                        verdict=summary,
                        passes=passes(call["role"], summary),
                        same_verdict=summary == recorded,
                    )
                    result.pop("output", None)
                    line["replays"].append(result)
                out.write(json.dumps(line, ensure_ascii=False) + "\n")
                out.flush()
                print(
                    call["role"],
                    Path(call["run"]).name,
                    "recorded",
                    line["recorded_passes"],
                    [(r["effort"], r.get("passes"), r.get("seconds")) for r in line["replays"]],
                    flush=True,
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("captures", nargs="+", help="run directories with raw-text captures")
    parser.add_argument("--roles", default="scope_validator,quantity_checker")
    parser.add_argument("--efforts", default="low,medium")
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--out", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
