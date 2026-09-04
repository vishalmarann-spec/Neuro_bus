from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Entity
from app.domain.extraction import EntityCandidate, normalized_entity_name


def merged_aliases(existing: list[str], incoming: list[str]) -> list[str]:
    aliases: dict[str, str] = {}
    for value in [*existing, *incoming]:
        normalized = normalized_entity_name(value)
        if normalized:
            aliases.setdefault(normalized, " ".join(value.split()))
    return sorted(aliases.values(), key=str.casefold)


async def resolve_entity(
    session: AsyncSession,
    candidate: EntityCandidate,
) -> Entity:
    normalized_name = normalized_entity_name(candidate.canonical_name)
    exact_result = await session.execute(
        select(Entity).where(
            Entity.entity_type == candidate.entity_type,
            Entity.normalized_name == normalized_name,
        )
    )
    entity = exact_result.scalar_one_or_none()

    if entity is None:
        same_type_result = await session.execute(
            select(Entity).where(Entity.entity_type == candidate.entity_type)
        )
        alias_matches = [
            existing
            for existing in same_type_result.scalars()
            if normalized_name in {normalized_entity_name(alias) for alias in existing.aliases}
        ]
        if len(alias_matches) == 1:
            entity = alias_matches[0]

    if entity is None:
        entity = Entity(
            entity_type=candidate.entity_type,
            canonical_name=candidate.canonical_name,
            normalized_name=normalized_name,
            aliases=candidate.aliases,
        )
        session.add(entity)
        await session.flush()
    else:
        entity.aliases = merged_aliases(entity.aliases, candidate.aliases)
    return entity
