import argparse
import json
from pathlib import Path

from app.evaluation.io import (
    load_gold_case_files,
    load_reasoning_scenarios,
    save_reasoning_report,
)
from app.evaluation.reasoning import evaluate_reasoning_scenarios


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate deterministic reasoning labels on fingerprint-bound source cases."
    )
    parser.add_argument("--gold", required=True, action="append", type=Path)
    parser.add_argument("--scenarios", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--require-human-verified", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    report = evaluate_reasoning_scenarios(
        load_reasoning_scenarios(args.scenarios),
        load_gold_case_files(args.gold),
    )
    if args.require_human_verified and report.diagnostic_only:
        parser.error("Reasoning scenarios or referenced source cases lack human verification.")

    rendered = json.dumps(report.model_dump(mode="json"), indent=2)
    if args.output:
        try:
            save_reasoning_report(args.output, report, overwrite=args.overwrite)
        except FileExistsError:
            parser.error("Output already exists; pass --overwrite to replace it.")
    else:
        print(rendered)
    if report.scenarios_passed != report.scenarios_total:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
