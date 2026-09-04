import pytest

from app.domain.provenance import (
    InvalidSourceURL,
    canonical_domain,
    canonicalize_url,
    segment_passages,
    sha256_text,
)


def test_canonicalize_url_removes_tracking_and_normalizes_host_and_path() -> None:
    result = canonicalize_url(
        "HTTPS://Example.EDU:443//programmes/../programmes/ai/?z=2&utm_source=test&a=1#fees"
    )

    assert result == "https://example.edu/programmes/ai?a=1&z=2"
    assert canonical_domain(result) == "example.edu"


@pytest.mark.parametrize(
    "value",
    ["javascript:alert(1)", "file:///etc/passwd", "https://user:secret@example.edu/page"],
)
def test_canonicalize_url_rejects_unsafe_shapes(value: str) -> None:
    with pytest.raises(InvalidSourceURL):
        canonicalize_url(value)


def test_passage_offsets_and_hashes_reproduce_exact_source_text() -> None:
    raw_content = (
        "AI security programmes are expanding.\nThe first paragraph keeps its line break.\n\n"
        "Employers increasingly list model-security skills."
    )

    passages = segment_passages(raw_content)

    assert len(passages) == 2
    for passage in passages:
        assert raw_content[passage.start_offset : passage.end_offset] == passage.exact_text
        assert passage.text_hash == sha256_text(passage.exact_text)


def test_long_blocks_are_split_without_losing_provenance() -> None:
    raw_content = " ".join(["evidence"] * 100)
    passages = segment_passages(raw_content, max_characters=220)

    assert len(passages) > 1
    assert all(len(item.exact_text) <= 220 for item in passages)
    assert all(
        raw_content[item.start_offset : item.end_offset] == item.exact_text for item in passages
    )
