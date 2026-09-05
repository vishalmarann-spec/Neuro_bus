import argparse
import json
import logging
from pathlib import Path

from app.evaluation.dataset import build_selection_manifest
from app.evaluation.io import load_gold_case_files
from app.evaluation.review import load_review_records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a locked development/validation/holdout manifest."
    )
    parser.add_argument("--gold", required=True, action="append", type=Path)
    parser.add_argument("--reviews", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    cases = load_gold_case_files(args.gold)
    try:
        manifest = build_selection_manifest(
            cases,
            load_review_records(args.reviews),
            dataset_id=args.dataset_id,
            seed=args.seed,
        )
    except ValueError as error:
        parser.error(str(error))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "dataset_id": manifest.dataset_id,
                "case_count": manifest.case_count,
                "split_counts": manifest.split_counts,
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
