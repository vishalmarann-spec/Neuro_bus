from app.services.insights import InsightBundle


def escape_markdown(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for character in ("`", "*", "_", "[", "]", "<", ">", "#"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def compact_text(value: str) -> str:
    return " ".join(value.split())


def quote_markdown(value: str) -> str:
    lines = value.splitlines() or [""]
    return "\n".join(f"> {escape_markdown(line)}" for line in lines)


def render_report_markdown(bundle: InsightBundle) -> str:
    insight = bundle.insight
    lines = [
        f"# {escape_markdown(compact_text(insight.title))}",
        "",
        f"- Status: `{insight.status.value}`",
        f"- Confidence: `{insight.confidence:.3f}`",
        f"- Generation version: `{insight.generation_version}`",
        f"- Created: `{insight.created_at.isoformat()}`",
        f"- Evidence fingerprint: `{insight.fingerprint}`",
    ]

    for index, record in enumerate(bundle.statements, start=1):
        statement = record.statement
        rendered_label = escape_markdown(statement.label.value.replace("_", " ").title())
        lines.extend(
            [
                "",
                f"## Finding {index}: {rendered_label}",
                "",
                escape_markdown(compact_text(statement.text)),
                "",
                f"Confidence: `{statement.confidence:.3f}`",
                "",
                "### Evidence",
            ]
        )
        for citation_index, citation in enumerate(record.citations, start=1):
            published = (
                citation.document.published_at.isoformat()
                if citation.document.published_at
                else "not supplied"
            )
            quality = (
                f"{citation.link.quality_score:.3f}"
                if citation.link.quality_score is not None
                else "not calculated"
            )
            lines.extend(
                [
                    "",
                    (
                        f"{citation_index}. **{citation.link.stance.value.title()}** — "
                        f"{escape_markdown(compact_text(citation.source.publisher))}"
                    ),
                    f"   - URL: `{escape_markdown(citation.document.canonical_url)}`",
                    f"   - Published: `{published}`",
                    f"   - Retrieved: `{citation.document.retrieved_at.isoformat()}`",
                    f"   - Document hash: `{citation.document.content_hash}`",
                    f"   - Evidence quality: `{quality}`",
                    "",
                    quote_markdown(citation.passage.exact_text),
                ]
            )

    lines.extend(
        [
            "",
            "---",
            "Generated deterministically from stored Neuro_Bus claims and evidence links.",
            "",
        ]
    )
    return "\n".join(lines)
