import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from pypdf import PdfReader

logger = logging.getLogger(__name__)
PDF_PARSER_VERSION = "pypdf.text.v1"


@dataclass(frozen=True, slots=True)
class PDFParseResult:
    text: str
    title: str | None
    page_count: int
    extracted_page_count: int
    parser_version: str = PDF_PARSER_VERSION

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Parsed PDF text cannot be blank.")
        if self.page_count < 1:
            raise ValueError("Parsed PDF page count must be positive.")
        if self.extracted_page_count < 1 or self.extracted_page_count > self.page_count:
            raise ValueError("Extracted PDF page count is invalid.")
        if not self.parser_version or len(self.parser_version) > 64:
            raise ValueError("PDF parser version is invalid.")
        if self.title is not None and len(self.title) > 500:
            raise ValueError("PDF title exceeds the metadata limit.")


class PDFParseFailure(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        page_count: int | None = None,
        extracted_page_count: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.page_count = page_count
        self.extracted_page_count = extracted_page_count


class PDFParser(Protocol):
    parser_version: str

    def parse(self, content: bytes) -> PDFParseResult: ...


@dataclass(frozen=True, slots=True)
class PyPDFTextParser:
    max_pages: int = 100
    max_output_characters: int = 2_000_000
    parser_version: str = PDF_PARSER_VERSION

    def __post_init__(self) -> None:
        if self.max_pages < 1:
            raise ValueError("PDF page limit must be positive.")
        if self.max_output_characters < 1_000:
            raise ValueError("PDF output limit must be at least 1,000 characters.")

    def parse(self, content: bytes) -> PDFParseResult:
        try:
            reader = PdfReader(BytesIO(content), strict=True)
        except Exception as error:
            logger.warning("pdf_parse_rejected", extra={"error_type": type(error).__name__})
            raise PDFParseFailure(
                "pdf_malformed", "PDF structure could not be parsed safely."
            ) from None

        try:
            encrypted = reader.is_encrypted
        except Exception as error:
            logger.warning(
                "pdf_encryption_check_failed", extra={"error_type": type(error).__name__}
            )
            raise PDFParseFailure(
                "pdf_malformed", "PDF encryption status could not be read safely."
            ) from None
        if encrypted:
            raise PDFParseFailure(
                "pdf_encrypted", "Encrypted PDFs are not supported by the public connector."
            )

        try:
            page_count = len(reader.pages)
        except Exception as error:
            logger.warning("pdf_page_count_failed", extra={"error_type": type(error).__name__})
            raise PDFParseFailure(
                "pdf_malformed", "PDF page structure could not be read safely."
            ) from None

        if page_count == 0:
            raise PDFParseFailure("pdf_no_pages", "PDF contains no pages.", page_count=0)
        if page_count > self.max_pages:
            raise PDFParseFailure(
                "pdf_page_limit_exceeded",
                "PDF exceeds the configured page limit.",
                page_count=page_count,
            )

        extracted_pages: list[str] = []
        output_characters = 0
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                raw_text = page.extract_text() or ""
            except Exception as error:
                logger.warning(
                    "pdf_page_extraction_failed",
                    extra={"page_number": page_number, "error_type": type(error).__name__},
                )
                raise PDFParseFailure(
                    "pdf_page_parse_failed",
                    "Text could not be extracted from a PDF page.",
                    page_count=page_count,
                    extracted_page_count=len(extracted_pages),
                ) from None

            page_text = self._normalize_text(raw_text)
            if not page_text:
                continue
            separator_size = 2 if extracted_pages else 0
            output_characters += separator_size + len(page_text)
            if output_characters > self.max_output_characters:
                raise PDFParseFailure(
                    "pdf_text_limit_exceeded",
                    "Extracted PDF text exceeds the configured limit.",
                    page_count=page_count,
                    extracted_page_count=len(extracted_pages),
                )
            extracted_pages.append(page_text)

        if not extracted_pages:
            raise PDFParseFailure(
                "pdf_no_extractable_text",
                "PDF contains no extractable text; OCR is not enabled.",
                page_count=page_count,
                extracted_page_count=0,
            )

        return PDFParseResult(
            text="\n\n".join(extracted_pages),
            title=self._read_title(reader),
            page_count=page_count,
            extracted_page_count=len(extracted_pages),
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        without_nulls = value.replace("\x00", "")
        blocks = re.split(r"(?:\r?\n)[ \t]*(?:\r?\n)+", without_nulls)
        normalized = [" ".join(block.split()) for block in blocks]
        return "\n\n".join(block for block in normalized if block).strip()

    @staticmethod
    def _read_title(reader: PdfReader) -> str | None:
        try:
            raw_title = reader.metadata.title if reader.metadata is not None else None
        except Exception:
            return None
        if raw_title is None:
            return None
        normalized = " ".join(str(raw_title).replace("\x00", "").split()).strip()
        return normalized[:500] or None
