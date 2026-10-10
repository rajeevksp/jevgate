"""Command-line interface for the Evidence Governor library (spec: "Library
packaged and installable separately from the app... a CLI").

No FastAPI, no app.core.settings -- reads its own configuration directly
from environment variables, so it works wherever the library is installed.

Usage:
    jevgate evaluate --input request.json [--policy NAME] [--output bundle.json]
    jevgate policies
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

import httpx

from jevgate.contracts import GovernorRequest
from jevgate.evaluate import EvaluationConfig, evaluate
from jevgate.jev.client import JevClient
from jevgate.jev.fixtures import JevFixtureStore
from jevgate.policy import DEFAULT_POLICY, POLICIES, get_policy


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() in ("1", "true", "yes")


def _build_jev_client(http_client: httpx.AsyncClient) -> JevClient:
    replay_mode = _env_bool("JEV_REPLAY_MODE", False)
    fixture_path = os.environ.get("JEV_FIXTURE_PATH", "tests/fixtures/jev")
    return JevClient(
        http_client,
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        model_id=os.environ.get("JEV_MODEL_ID", "typesafe/jev-1.13"),
        concurrency=int(os.environ.get("JEV_CONCURRENCY", "8")),
        per_call_timeout_s=float(os.environ.get("JEV_PER_CALL_TIMEOUT_S", "15")),
        retry_count=int(os.environ.get("JEV_RETRY_COUNT", "3")),
        replay_mode=replay_mode,
        fixture_store=JevFixtureStore(fixture_path) if replay_mode else None,
    )


def _config_from_env() -> EvaluationConfig:
    return EvaluationConfig(
        max_passage_chars=int(os.environ.get("MAX_PASSAGE_CHARS", "24000")),
        allow_truncation=_env_bool("ALLOW_TEXT_TRUNCATION", True),
        conflict_budget_share=float(os.environ.get("CONFLICT_BUDGET_SHARE", "0.25")),
        dedup_similarity_threshold=float(os.environ.get("DEDUP_SIMILARITY_THRESHOLD", "0.9")),
        tokenizer_name=os.environ.get("BUDGET_TOKENIZER_NAME", "cl100k_base"),
    )


async def _run_evaluate(args: argparse.Namespace) -> None:
    with open(args.input, encoding="utf-8") as f:
        request = GovernorRequest.model_validate(json.load(f))

    policy = get_policy(args.policy) if args.policy else DEFAULT_POLICY
    config = _config_from_env()

    async with httpx.AsyncClient() as http_client:
        jev_client = _build_jev_client(http_client)
        bundle = await evaluate(request, jev_client, policy, config)

    output = bundle.model_dump_json(indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Bundle written to {args.output}", file=sys.stderr)
    else:
        print(output)


def _run_policies() -> None:
    for policy in POLICIES.values():
        print(f"{policy.full_name}\t{policy.thresholds}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="jevgate", description="Evidence Governor CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate a GovernorRequest JSON file")
    evaluate_parser.add_argument(
        "--input", required=True, help="Path to a GovernorRequest JSON file"
    )
    evaluate_parser.add_argument("--policy", default=None, help="Named policy (default: built-in)")
    evaluate_parser.add_argument(
        "--output", default=None, help="Write bundle JSON here, not stdout"
    )

    subparsers.add_parser("policies", help="List available policies")

    args = parser.parse_args()
    if args.command == "evaluate":
        asyncio.run(_run_evaluate(args))
    elif args.command == "policies":
        _run_policies()


if __name__ == "__main__":
    main()
