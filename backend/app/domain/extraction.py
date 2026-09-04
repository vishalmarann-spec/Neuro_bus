import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.models import EntityType, EvidenceStance, Passage


class ExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MentionCandidate(ExtractionModel):
    passage_ordinal: int = Field(ge=0)
    surface_text: str = Field(min_length=1, max_length=500)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)


class EntityCandidate(ExtractionModel):
    local_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    entity_type: EntityType
    canonical_name: str = Field(min_length=1, max_length=500)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    mentions: list[MentionCandidate] = Field(default_factory=list)

    @field_validator("canonical_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        return " ".join(value.split())


class EvidenceCandidate(ExtractionModel):
    passage_ordinal: int = Field(ge=0)
    stance: EvidenceStance
    directness: float = Field(ge=0, le=1)
    extraction_confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1)


class ClaimCandidate(ExtractionModel):
    subject_local_id: str | None = None
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]{1,159}$")
    object_value: dict[str, Any] = Field(default_factory=dict)
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    normalized_text: str = Field(min_length=3)
    extraction_confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceCandidate] = Field(min_length=1)


class ExtractionEnvelope(ExtractionModel):
    entities: list[EntityCandidate] = Field(default_factory=list)
    claims: list[ClaimCandidate] = Field(default_factory=list)


def normalized_entity_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def validate_provenance(
    extraction: ExtractionEnvelope,
    passages: list[Passage],
) -> list[str]:
    errors: list[str] = []
    passages_by_ordinal = {passage.ordinal: passage for passage in passages}
    entity_ids = [entity.local_id for entity in extraction.entities]
    if len(set(entity_ids)) != len(entity_ids):
        errors.append("Entity local_id values must be unique.")

    for entity in extraction.entities:
        if not normalized_entity_name(entity.canonical_name):
            errors.append(f"Entity {entity.local_id} has no normalizable name.")
        for mention in entity.mentions:
            passage = passages_by_ordinal.get(mention.passage_ordinal)
            if passage is None:
                errors.append(
                    f"Entity {entity.local_id} references missing passage "
                    f"{mention.passage_ordinal}."
                )
                continue
            if mention.end_offset <= mention.start_offset:
                errors.append(f"Entity {entity.local_id} has an invalid mention range.")
                continue
            actual = passage.exact_text[mention.start_offset : mention.end_offset]
            if actual != mention.surface_text:
                errors.append(
                    f"Entity {entity.local_id} mention text does not match passage "
                    f"{mention.passage_ordinal} offsets."
                )

    known_entity_ids = set(entity_ids)
    for index, claim in enumerate(extraction.claims):
        if claim.subject_local_id and claim.subject_local_id not in known_entity_ids:
            errors.append(f"Claim {index} references unknown subject {claim.subject_local_id}.")
        usable_evidence = 0
        for evidence in claim.evidence:
            if evidence.passage_ordinal not in passages_by_ordinal:
                errors.append(
                    f"Claim {index} references missing passage {evidence.passage_ordinal}."
                )
            elif evidence.stance != EvidenceStance.IRRELEVANT:
                usable_evidence += 1
        if usable_evidence == 0:
            errors.append(f"Claim {index} has no usable supporting/contextual evidence.")

    return errors
