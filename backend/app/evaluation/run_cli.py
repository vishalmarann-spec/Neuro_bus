import argparse
import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.evaluation.io import load_gold_case_files, save_benchmark_run
from app.evaluation.review import apply_latest_reviews, load_review_records
from app.evaluation.runner import run_benchmark_artifact
from app.providers.factory import create_model_provider


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate extraction predictions with the configured live model provider."
    )
    parser.add_argument("--gold", required=True, action="append", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pricing-basis")
    parser.add_argument("--allow-assistant-verified-diagnostic", action="store_true")
    parser.add_argument("--confirm-live-api-cost", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1.")
    if args.output.exists() and not args.overwrite:
        parser.error("Output already exists; pass --overwrite to replace it.")

    cases = load_gold_case_files(args.gold)
    if args.reviews:
        cases = apply_latest_reviews(cases, load_review_records(args.reviews))
    if args.case_id:
        requested = set(args.case_id)
        known = {case.case_id for case in cases}
        missing = sorted(requested - known)
        if missing:
            parser.error("Unknown --case-id values: " + ", ".join(missing))
        cases = [case for case in cases if case.case_id in requested]
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        parser.error("No benchmark cases were selected.")

    diagnostic_only = not all(case.review_status == "human_verified" for case in cases)
    if diagnostic_only and not args.allow_assistant_verified_diagnostic:
        parser.error(
            "Selected cases are not all human-verified; pass "
            "--allow-assistant-verified-diagnostic for a non-selection run."
        )

    settings = get_settings()
    if settings.model_input_cost_per_million_usd is not None and not args.pricing_basis:
        parser.error("Configured cost estimates require --pricing-basis.")
    try:
        provider = create_model_provider(settings)
    except ValueError as error:
        parser.error(str(error))
    if provider.provider_name == "disabled":
        parser.error("Configure MODEL_PROVIDER before running a live benchmark.")
    if not args.confirm_live_api_cost:
        parser.error("Pass --confirm-live-api-cost to authorize provider requests.")

    artifact = asyncio.run(
        run_benchmark_artifact(
            provider,
            cases,
            diagnostic_only=diagnostic_only,
            pricing_basis=args.pricing_basis,
        )
    )
    save_benchmark_run(args.output, artifact, overwrite=args.overwrite)
    print(
        f"Saved {len(artifact.predictions)} predictions and {len(artifact.failures)} failures "
        f"to {args.output}."
    )
    if artifact.failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
