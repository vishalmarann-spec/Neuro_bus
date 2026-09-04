import argparse
import json
from pathlib import Path

from app.evaluation.io import load_gold_cases, load_predictions
from app.evaluation.metrics import score_models


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score Neuro_Bus extraction predictions.")
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    scorecards = score_models(load_gold_cases(args.gold), load_predictions(args.predictions))
    rendered = json.dumps([scorecard.model_dump(mode="json") for scorecard in scorecards], indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
