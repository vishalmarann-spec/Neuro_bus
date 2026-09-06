from collections import Counter, defaultdict
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class IndependenceDocument:
    document_id: UUID
    source_id: UUID
    content_hash: str
    publisher_family: str | None = None
    upstream_urls: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IndependenceAssignment:
    group: str
    reasons: tuple[str, ...]


def normalize_publisher_family(value: str) -> str:
    return " ".join(value.split()).casefold()


def _signals(document: IndependenceDocument) -> set[str]:
    signals = {
        f"source:{document.source_id}",
        f"content:{document.content_hash}",
    }
    if document.publisher_family:
        signals.add(f"publisher-family:{normalize_publisher_family(document.publisher_family)}")
    signals.update(f"upstream:{url}" for url in document.upstream_urls)
    return signals


def _preferred_group(reasons: tuple[str, ...]) -> str:
    priority = ("upstream:", "content:", "publisher-family:", "source:")
    for prefix in priority:
        candidates = [reason for reason in reasons if reason.startswith(prefix)]
        if candidates:
            return min(candidates)
    raise ValueError("An independence assignment must have at least one reason.")


def assign_independence_groups(
    documents: list[IndependenceDocument],
) -> dict[UUID, IndependenceAssignment]:
    """Group documents by explicit, reviewable dependency signals.

    Dependence is transitive: if two documents share a publisher family and one also shares an
    upstream study with a third document, all three belong to one independence component.
    """

    if not documents:
        return {}

    by_id = {document.document_id: document for document in documents}
    if len(by_id) != len(documents):
        raise ValueError("Document identifiers must be unique.")

    parents = {document_id: document_id for document_id in by_id}

    def find(document_id: UUID) -> UUID:
        parent = parents[document_id]
        if parent != document_id:
            parents[document_id] = find(parent)
        return parents[document_id]

    def union(left: UUID, right: UUID) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[max(left_root, right_root, key=str)] = min(left_root, right_root, key=str)

    document_signals = {document.document_id: _signals(document) for document in documents}
    owners: dict[str, UUID] = {}
    signal_counts: Counter[str] = Counter()
    for document_id, signals in document_signals.items():
        for signal in signals:
            signal_counts[signal] += 1
            owner = owners.setdefault(signal, document_id)
            union(owner, document_id)

    component_ids: dict[UUID, list[UUID]] = defaultdict(list)
    for document_id in by_id:
        component_ids[find(document_id)].append(document_id)

    assignments: dict[UUID, IndependenceAssignment] = {}
    for component in component_ids.values():
        shared_reasons = sorted(
            {
                signal
                for document_id in component
                for signal in document_signals[document_id]
                if signal_counts[signal] > 1
            }
        )
        if not shared_reasons:
            only_document = component[0]
            shared_reasons = [f"source:{by_id[only_document].source_id}"]
        reasons = tuple(shared_reasons)
        assignment = IndependenceAssignment(group=_preferred_group(reasons), reasons=reasons)
        for document_id in component:
            assignments[document_id] = assignment
    return assignments
