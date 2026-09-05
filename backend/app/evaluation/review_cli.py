import argparse
import logging
from pathlib import Path

from app.evaluation.io import load_gold_cases
from app.evaluation.review import (
    ReviewChecklist,
    append_review_record,
    create_review_record,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append a human benchmark-review decision bound to the exact gold case."
    )
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument(
        "--decision",
        required=True,
        choices=("approved", "changes_requested", "rejected"),
    )
    parser.add_argument("--notes", required=True)
    parser.add_argument("--source-url-opened", action="store_true")
    parser.add_argument("--excerpt-matches-source", action="store_true")
    parser.add_argument("--entities-and-claims-checked", action="store_true")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args()
    loaded_cases = load_gold_cases(args.gold)
    cases = {case.case_id: case for case in loaded_cases}
    if len(cases) != len(loaded_cases):
        parser.error(f"duplicate case_id values found in {args.gold}")
    case = cases.get(args.case_id)
    if case is None:
        parser.error(f"case_id {args.case_id!r} was not found in {args.gold}")

    checklist = ReviewChecklist(
        source_url_opened=args.source_url_opened,
        excerpt_matches_source=args.excerpt_matches_source,
        entities_and_claims_checked=args.entities_and_claims_checked,
    )
    try:
        record = create_review_record(
            case,
            reviewer=args.reviewer,
            decision=args.decision,
            checklist=checklist,
            notes=args.notes,
        )
        append_review_record(args.ledger, record)
    except ValueError as error:
        parser.error(str(error))
    print(record.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
