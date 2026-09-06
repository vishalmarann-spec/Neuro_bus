from uuid import UUID

import pytest

from app.domain.independence import IndependenceDocument, assign_independence_groups


def document(
    identifier: int,
    *,
    source: int,
    content: str,
    family: str | None = None,
    upstream: tuple[str, ...] = (),
) -> IndependenceDocument:
    return IndependenceDocument(
        document_id=UUID(int=identifier),
        source_id=UUID(int=source),
        content_hash=f"sha256:{content}",
        publisher_family=family,
        upstream_urls=upstream,
    )


def test_dependency_signals_are_transitive_and_reviewable() -> None:
    shared_study = "https://research.example/studies/ai-demand"
    assignments = assign_independence_groups(
        [
            document(1, source=11, content="a", family="Example Media Group"),
            document(
                2,
                source=12,
                content="b",
                family=" example   media group ",
                upstream=(shared_study,),
            ),
            document(3, source=13, content="c", upstream=(shared_study,)),
        ]
    )

    assert len({item.group for item in assignments.values()}) == 1
    assert assignments[UUID(int=1)].group == f"upstream:{shared_study}"
    assert assignments[UUID(int=1)].reasons == (
        "publisher-family:example media group",
        f"upstream:{shared_study}",
    )


def test_unrelated_documents_remain_independent() -> None:
    assignments = assign_independence_groups(
        [
            document(1, source=11, content="a"),
            document(2, source=12, content="b"),
        ]
    )

    assert assignments[UUID(int=1)].group == f"source:{UUID(int=11)}"
    assert assignments[UUID(int=2)].group == f"source:{UUID(int=12)}"


def test_duplicate_document_identifiers_fail_closed() -> None:
    with pytest.raises(ValueError, match="identifiers must be unique"):
        assign_independence_groups(
            [
                document(1, source=11, content="a"),
                document(1, source=12, content="b"),
            ]
        )
