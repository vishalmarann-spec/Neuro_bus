import argparse
import json
from pathlib import Path

from app.evaluation.coverage import summarize_benchmark_coverage
from app.evaluation.io import load_gold_case_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Neuro_Bus benchmark coverage.")
    parser.add_argument("--gold", required=True, action="append", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-selection-ready",
        action="store_true",
        help="Exit with an error unless all selection-grade coverage gates pass.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    report = summarize_benchmark_coverage(load_gold_case_files(args.gold))
    rendered = json.dumps(report.model_dump(mode="json"), indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    if args.require_selection_ready and not report.selection_ready:
        parser.error("; ".join(report.failures))


if __name__ == "__main__":
    main()
