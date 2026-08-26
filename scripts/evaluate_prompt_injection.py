"""Run the reproducible Sprint 25 prompt-injection evaluation.

Example:
    python -m scripts.evaluate_prompt_injection \
      --prompt-version v3 --mode strict \
      --output artifacts/security-sprint25/adversarial-results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.evaluation.generation_metrics import build_default_metrics, compute_generation_metrics
from app.evaluation.prompt_injection import (
    SecurityCaseResult,
    aggregate_security_metrics,
    dataset_summary,
    evaluate_case,
    load_adversarial_dataset,
    search_results_for_case,
)
from app.llm.generate import stream_answer
from app.llm.grounding import check_grounding
from app.llm.ollama_client import OllamaClient
from app.llm.prompt import NOT_FOUND_PHRASE
from app.llm.trust_boundary import estimate_context_overhead
from app.shared.config import settings

DEFAULT_DATASET = "tests/fixtures/security_sprint25/adversarial.json"
DEFAULT_OUTPUT = "artifacts/security-sprint25/adversarial-results.json"
DEFAULT_BENIGN_OUTPUT = "artifacts/security-sprint25/benign-regression.json"


async def _generate(client: OllamaClient, case: dict, prompt_version: str, mode: str) -> str:
    parts: list[str] = []
    async for event in stream_answer(
        case["user_query"],
        search_results_for_case(case),
        client,
        model=settings.ollama_model,
        prompt_version=prompt_version,
        validation_mode=mode,
        injection_eval_category=case["category"],
    ):
        if event["type"] == "token":
            parts.append(event["content"])
    return "".join(parts)


async def run(args: argparse.Namespace) -> dict:
    all_cases = load_adversarial_dataset(args.dataset)
    cases = all_cases[args.offset :]
    if args.max_cases:
        cases = cases[: args.max_cases]
    client = OllamaClient(base_url=settings.ollama_base_url)
    results = []
    try:
        for index, case in enumerate(cases, 1):
            answer = await _generate(client, case, args.prompt_version, args.mode)
            result = evaluate_case(case, answer, args.prompt_version, args.mode)
            results.append(result)
            print(f"[{index}/{len(cases)}] {case['case_id']} {'PASS' if result.passed else 'FAIL'}")
    finally:
        await client.aclose()

    combined_results = results
    if args.append and Path(args.output).exists():
        previous = json.loads(Path(args.output).read_text())
        combined_results = [
            SecurityCaseResult(
                case_id=row["case_id"],
                category=row["category"],
                language=row["language"],
                passed=row["pass"],
                forbidden_behavior_triggered=row["forbidden_behavior_triggered"],
                citations_valid=row["citations_valid"],
                output_policy_passed=row["output_policy_passed"],
                blocked_by_output_policy=row.get("blocked_by_output_policy", False),
                citation_count=row["citation_count"],
            )
            for row in previous.get("results", [])
        ] + results
    aggregate = aggregate_security_metrics(combined_results)
    overhead_samples = [
        estimate_context_overhead(search_results_for_case(case)) for case in all_cases
    ]
    overhead = {
        "estimator": "whitespace_token_estimate",
        "old_tokens": sum(sample["old_tokens"] for sample in overhead_samples),
        "new_tokens": sum(sample["new_tokens"] for sample in overhead_samples),
    }
    overhead["overhead_percent"] = round(
        (overhead["new_tokens"] - overhead["old_tokens"])
        / overhead["old_tokens"]
        * 100,
        2,
    )
    return {
        "schema_version": "sprint25.security-evaluation.v1",
        "dataset": args.dataset,
        "prompt_version": args.prompt_version,
        "mode": args.mode,
        "dataset_total_count": len(all_cases),
        "evaluation_complete": len(combined_results) == len(all_cases),
        **dataset_summary(all_cases),
        "context_overhead": overhead,
        **aggregate,
        "results": [result.as_dict() for result in combined_results],
    }


async def run_benign_regression(args: argparse.Namespace) -> dict:
    cases = [
        case
        for case in load_adversarial_dataset(args.dataset)
        if case["category"] == "benign_control"
    ]
    client = OllamaClient(base_url=settings.ollama_base_url)
    judge_metrics = (
        build_default_metrics(
            judge_model_name=settings.eval_judge_model,
            base_url=settings.ollama_base_url,
        )
        if args.with_judge
        else None
    )
    versions: dict[str, list[dict]] = {}
    try:
        for version in ("v2", "v3"):
            version_results = []
            for case in cases:
                answer = await _generate(client, case, version, args.mode)
                chunks = search_results_for_case(case)
                grounding = check_grounding(answer, chunks)
                judged = (
                    compute_generation_metrics(
                        case["user_query"],
                        answer,
                        [chunk.payload["text"] for chunk in chunks],
                        judge_metrics,
                    )
                    if judge_metrics
                    else {}
                )
                version_results.append(
                    {
                        "case_id": case["case_id"],
                        "answer_relevancy": judged.get("answer_relevancy"),
                        "citation_integrity": grounding.citations_valid,
                        "not_found_behavior": (
                            not case["should_answer"]
                            and NOT_FOUND_PHRASE.casefold() in answer.casefold()
                        ),
                    }
                )
            versions[version] = version_results
    finally:
        await client.aclose()

    def aggregate(version: str) -> dict:
        rows = versions[version]
        return {
            "answer_relevancy": (
                sum(row["answer_relevancy"] for row in rows if row["answer_relevancy"] is not None)
                / sum(row["answer_relevancy"] is not None for row in rows)
                if any(row["answer_relevancy"] is not None for row in rows)
                else None
            ),
            "citation_integrity": sum(row["citation_integrity"] for row in rows) / len(rows),
            "not_found_behavior": sum(
                row["not_found_behavior"] for row in rows if row["case_id"] == "benign-015"
            ),
            "judge": settings.eval_judge_model if args.with_judge else "not measured",
        }

    baseline = aggregate("v2")
    candidate = aggregate("v3")
    return {
        "schema_version": "sprint25.benign-regression.v1",
        "dataset": args.dataset,
        "case_count": len(cases),
        "baseline": {"prompt_version": "v2", "metrics": baseline},
        "candidate": {"prompt_version": "v3", "metrics": candidate},
        "delta": {
            key: (
                candidate[key] - baseline[key]
                if isinstance(candidate[key], int | float)
                and isinstance(baseline[key], int | float)
                else None
            )
            for key in ("answer_relevancy", "citation_integrity", "not_found_behavior")
        },
        "cases": versions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate prompt injection resistance")
    parser.add_argument("--prompt-version", default="v3", choices=["v1", "v2", "v3"])
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--mode", default="fast", choices=["fast", "strict"])
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--benign-output", default=DEFAULT_BENIGN_OUTPUT)
    parser.add_argument("--benign-regression", action="store_true")
    parser.add_argument("--with-judge", action="store_true")
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--append", action="store_true")
    args = parser.parse_args()
    if args.benign_regression:
        result = asyncio.run(run_benign_regression(args))
    else:
        result = asyncio.run(run(args))
    output = Path(args.benign_output if args.benign_regression else args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    if args.benign_regression:
        print(json.dumps(result["delta"], indent=2))
    else:
        print(json.dumps(result["metrics"], indent=2))


if __name__ == "__main__":
    main()
