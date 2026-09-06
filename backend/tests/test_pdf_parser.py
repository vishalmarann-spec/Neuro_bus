from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.services.pdf_parser import PDFParseFailure, PyPDFTextParser


def build_pdf(
    page_texts: list[str], *, title: str | None = None, password: str | None = None
) -> bytes:
    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        if text:
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            font_reference = writer._add_object(font)
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
            )
            escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1"))
            page[NameObject("/Contents")] = writer._add_object(stream)
    if title is not None:
        writer.add_metadata({"/Title": title})
    if password is not None:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_parser_extracts_pages_title_and_auditable_counts() -> None:
    content = build_pdf(
        ["AI security demand increased.", "Universities launched new courses."],
        title="  University   evidence report  ",
    )

    result = PyPDFTextParser().parse(content)

    assert result.text == ("AI security demand increased.\n\nUniversities launched new courses.")
    assert result.title == "University evidence report"
    assert result.page_count == 2
    assert result.extracted_page_count == 2
    assert result.parser_version == "pypdf.text.v1"


def test_pdf_parser_rejects_encrypted_content_without_attempting_a_password() -> None:
    content = build_pdf(["Private evidence"], password="secret")

    with pytest.raises(PDFParseFailure) as failure:
        PyPDFTextParser().parse(content)

    assert failure.value.code == "pdf_encrypted"
    assert str(failure.value) == "Encrypted PDFs are not supported by the public connector."


def test_pdf_parser_reports_image_only_or_blank_documents_without_fake_text() -> None:
    content = build_pdf(["", ""])

    with pytest.raises(PDFParseFailure) as failure:
        PyPDFTextParser().parse(content)

    assert failure.value.code == "pdf_no_extractable_text"
    assert failure.value.page_count == 2
    assert failure.value.extracted_page_count == 0


def test_pdf_parser_enforces_page_limit_before_extraction() -> None:
    content = build_pdf(["one", "two"])

    with pytest.raises(PDFParseFailure) as failure:
        PyPDFTextParser(max_pages=1).parse(content)

    assert failure.value.code == "pdf_page_limit_exceeded"
    assert failure.value.page_count == 2


def test_pdf_parser_enforces_parsed_text_limit() -> None:
    content = build_pdf(["a" * 1_100])

    with pytest.raises(PDFParseFailure) as failure:
        PyPDFTextParser(max_output_characters=1_000).parse(content)

    assert failure.value.code == "pdf_text_limit_exceeded"
    assert failure.value.page_count == 1
    assert failure.value.extracted_page_count == 0


@pytest.mark.parametrize("content", [b"%PDF-1.7", b"not a pdf"])
def test_pdf_parser_rejects_malformed_input(content: bytes) -> None:
    with pytest.raises(PDFParseFailure) as failure:
        PyPDFTextParser().parse(content)

    assert failure.value.code == "pdf_malformed"
