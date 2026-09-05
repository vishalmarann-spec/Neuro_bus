import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.evaluation.models import GoldCase, ModelPrediction

ModelT = TypeVar("ModelT", bound=BaseModel)


def _load_records(path: Path) -> list[object]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        loaded = json.loads(text)
        if not isinstance(loaded, list):
            raise ValueError("JSON benchmark input must be an array.")
        return loaded
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _validate_records(path: Path, model: type[ModelT]) -> list[ModelT]:
    return [model.model_validate(record) for record in _load_records(path)]


def load_gold_cases(path: Path) -> list[GoldCase]:
    return _validate_records(path, GoldCase)


def load_gold_case_files(paths: list[Path]) -> list[GoldCase]:
    cases = [case for path in paths for case in load_gold_cases(path)]
    case_ids = [case.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Gold case_id values must be unique across all input files.")
    return cases


def load_predictions(path: Path) -> list[ModelPrediction]:
    return _validate_records(path, ModelPrediction)


def save_predictions(path: Path, predictions: list[ModelPrediction]) -> None:
    payload = [prediction.model_dump(mode="json") for prediction in predictions]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
