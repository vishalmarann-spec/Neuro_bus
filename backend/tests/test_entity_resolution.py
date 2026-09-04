import pytest
from sqlalchemy import select

from app.core.models import Entity, EntityType
from app.domain.extraction import EntityCandidate
from app.services.entity_resolution import resolve_entity


@pytest.mark.asyncio
async def test_exact_alias_resolves_to_existing_entity(session_factory) -> None:
    async with session_factory() as session:
        existing = Entity(
            entity_type=EntityType.UNIVERSITY,
            canonical_name="Massachusetts Institute of Technology",
            normalized_name="massachusetts institute of technology",
            aliases=["MIT"],
        )
        session.add(existing)
        await session.commit()
        existing_id = existing.id

        resolved = await resolve_entity(
            session,
            EntityCandidate(
                local_id="university_1",
                entity_type=EntityType.UNIVERSITY,
                canonical_name="MIT",
                aliases=["M.I.T."],
                mentions=[],
            ),
        )
        await session.commit()

        assert resolved.id == existing_id
        entities = (await session.execute(select(Entity))).scalars().all()
        assert len(entities) == 1
        assert entities[0].aliases == ["M.I.T.", "MIT"]


@pytest.mark.asyncio
async def test_ambiguous_alias_does_not_merge_entities(session_factory) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                Entity(
                    entity_type=EntityType.ORGANIZATION,
                    canonical_name="Alpha Institute",
                    normalized_name="alpha institute",
                    aliases=["AI"],
                ),
                Entity(
                    entity_type=EntityType.ORGANIZATION,
                    canonical_name="Applied Intelligence",
                    normalized_name="applied intelligence",
                    aliases=["AI"],
                ),
            ]
        )
        await session.commit()

        resolved = await resolve_entity(
            session,
            EntityCandidate(
                local_id="organization_1",
                entity_type=EntityType.ORGANIZATION,
                canonical_name="AI",
                aliases=[],
                mentions=[],
            ),
        )
        await session.commit()

        entities = (await session.execute(select(Entity))).scalars().all()
        assert len(entities) == 3
        assert resolved.canonical_name == "AI"
