"""Extracts structured content from PDF files using pdfplumber."""

from dataclasses import dataclass, field
from typing import List, Optional
import pdfplumber


@dataclass
class RawTextBlock:
    text: str
    font_size: Optional[float] = None
    is_bold: bool = False
    page_num: int = 0


@dataclass
class RawTable:
    rows: List[List[str]] = field(default_factory=list)
    page_num: int = 0


@dataclass
class ParsedDocument:
    text_blocks: List[RawTextBlock] = field(default_factory=list)
    tables: List[RawTable] = field(default_factory=list)
    page_count: int = 0
    page_width_mm: float = 210.0
    page_height_mm: float = 297.0


def _pts_to_mm(pts: float) -> float:
    return pts * 25.4 / 72.0


def parse_pdf(pdf_path: str) -> ParsedDocument:
    doc = ParsedDocument()

    with pdfplumber.open(pdf_path) as pdf:
        doc.page_count = len(pdf.pages)

        if pdf.pages:
            first = pdf.pages[0]
            doc.page_width_mm = round(_pts_to_mm(first.width), 1)
            doc.page_height_mm = round(_pts_to_mm(first.height), 1)

        for page_num, page in enumerate(pdf.pages):
            # Extract tables before text so we can skip table-region text
            page_tables = page.extract_tables()
            for raw_rows in page_tables:
                cleaned_rows = [
                    [str(cell or "").strip() for cell in row]
                    for row in raw_rows
                    if any(cell for cell in row)
                ]
                if cleaned_rows:
                    doc.tables.append(RawTable(rows=cleaned_rows, page_num=page_num))

            # Extract text with character-level font info
            words = page.extract_words(
                extra_attrs=["size", "fontname"],
                use_text_flow=True,
            )
            if not words:
                continue

            # Group words into lines by vertical position (y0)
            lines: dict[int, list] = {}
            for w in words:
                y_bucket = round(w["top"] / 3) * 3
                lines.setdefault(y_bucket, []).append(w)

            for y_key in sorted(lines):
                line_words = lines[y_key]
                text = " ".join(w["text"] for w in line_words).strip()
                if not text:
                    continue

                sizes = [w.get("size") for w in line_words if w.get("size")]
                avg_size = sum(sizes) / len(sizes) if sizes else None

                fonts = [w.get("fontname", "") for w in line_words]
                is_bold = any(
                    "Bold" in f or "bold" in f or "Black" in f for f in fonts
                )

                doc.text_blocks.append(
                    RawTextBlock(
                        text=text,
                        font_size=avg_size,
                        is_bold=is_bold,
                        page_num=page_num,
                    )
                )

    return doc


def to_prompt_text(doc: ParsedDocument) -> str:
    """Converts parsed document into a compact text representation for LLM input."""
    lines: List[str] = [
        f"[문서 정보] 페이지 수: {doc.page_count}, "
        f"용지 크기: {doc.page_width_mm}×{doc.page_height_mm}mm",
        "",
    ]

    if doc.text_blocks:
        lines.append("[텍스트 블록]")
        # Determine heading font size threshold: top 15% of sizes
        sizes = [b.font_size for b in doc.text_blocks if b.font_size]
        size_threshold = sorted(sizes, reverse=True)[max(0, len(sizes) // 7)] if sizes else 999

        for block in doc.text_blocks:
            tag = ""
            if block.font_size and block.font_size >= size_threshold:
                tag = "[대제목]"
            elif block.is_bold:
                tag = "[소제목]"
            lines.append(f"{tag}{block.text}")

    if doc.tables:
        lines.append("")
        lines.append("[표 목록]")
        for i, tbl in enumerate(doc.tables, 1):
            lines.append(f"표 {i} (페이지 {tbl.page_num + 1}):")
            for row in tbl.rows[:6]:  # first 6 rows for brevity
                lines.append("  | " + " | ".join(row) + " |")
            if len(tbl.rows) > 6:
                lines.append(f"  ... (총 {len(tbl.rows)}행)")

    return "\n".join(lines)
