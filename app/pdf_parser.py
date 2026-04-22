"""Extracts structured content from PDF files using PyMuPDF (fitz).

PyMuPDF provides block-level layout analysis with per-span font metadata
(size, bold, position), which lets us classify headings without an ML model.
Table detection uses PyMuPDF's built-in finder (>= 1.23).
"""

from dataclasses import dataclass, field
from typing import List, Optional
import fitz  # PyMuPDF


_FLAG_BOLD = 1 << 4   # bit 4 of MuPDF font flags = bold
_PTS_TO_MM = 25.4 / 72.0


def _mm(pts: float) -> float:
    return round(pts * _PTS_TO_MM, 1)


@dataclass
class RawTextBlock:
    text: str
    font_size: float = 10.0
    is_bold: bool = False
    # Normalised vertical position (0 = top, 1 = bottom of page)
    y_ratio: float = 0.0
    page_num: int = 0


@dataclass
class RawTable:
    rows: List[List[str]] = field(default_factory=list)
    bbox: tuple = field(default_factory=tuple)   # (x0, y0, x1, y1) in pts
    y_ratio: float = 0.0                         # normalised vertical position (0=top)
    page_num: int = 0


@dataclass
class ParsedDocument:
    text_blocks: List[RawTextBlock] = field(default_factory=list)
    tables: List[RawTable] = field(default_factory=list)
    page_count: int = 0
    page_width_mm: float = 210.0
    page_height_mm: float = 297.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _spans_to_block(spans: list, page_h: float, page_num: int, y_top: float) -> Optional[RawTextBlock]:
    """Merge a list of fitz spans into one RawTextBlock."""
    text_parts = []
    sizes = []
    bold_votes = 0

    for sp in spans:
        t = sp["text"].strip()
        if not t:
            continue
        text_parts.append(t)
        sizes.append(sp["size"])
        if sp["flags"] & _FLAG_BOLD:
            bold_votes += 1

    text = " ".join(text_parts).strip()
    if not text:
        return None

    avg_size = sum(sizes) / len(sizes) if sizes else 10.0
    is_bold = bold_votes > len(spans) / 2  # majority of spans are bold
    y_ratio = y_top / page_h if page_h else 0.0

    return RawTextBlock(
        text=text,
        font_size=round(avg_size, 1),
        is_bold=is_bold,
        y_ratio=y_ratio,
        page_num=page_num,
    )


def _table_bbox_set(tables: List[RawTable]) -> list:
    return [t.bbox for t in tables]


def _in_table(block_bbox: tuple, table_bboxes: list, tolerance: float = 2.0) -> bool:
    """Return True if a text block overlaps with any table bounding box."""
    bx0, by0, bx1, by1 = block_bbox
    for tx0, ty0, tx1, ty1 in table_bboxes:
        if bx0 < tx1 - tolerance and bx1 > tx0 + tolerance \
                and by0 < ty1 - tolerance and by1 > ty0 + tolerance:
            return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_pdf(pdf_path: str) -> ParsedDocument:
    doc = ParsedDocument()

    with fitz.open(pdf_path) as pdf:
        doc.page_count = len(pdf)

        if pdf.page_count:
            first = pdf[0]
            doc.page_width_mm = _mm(first.rect.width)
            doc.page_height_mm = _mm(first.rect.height)

        for page_num in range(len(pdf)):
            page = pdf[page_num]
            page_h = page.rect.height

            # ── 1. Table detection ──────────────────────────────────────────
            page_tables: List[RawTable] = []
            try:
                for tbl in page.find_tables():
                    rows = tbl.extract()
                    cleaned = [
                        [str(cell or "").strip() for cell in row]
                        for row in rows
                        if any(cell for cell in row)
                    ]
                    if cleaned:
                        y_ratio = tbl.bbox[1] / page_h if page_h else 0.0
                        page_tables.append(
                            RawTable(rows=cleaned, bbox=tbl.bbox,
                                     y_ratio=y_ratio, page_num=page_num)
                        )
            except Exception:
                pass  # find_tables() not available for this page type

            doc.tables.extend(page_tables)
            tbl_bboxes = _table_bbox_set(page_tables)

            # ── 2. Text block extraction ────────────────────────────────────
            raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            for block in raw.get("blocks", []):
                if block.get("type") != 0:   # type 1 = image, skip
                    continue

                block_bbox = (
                    block["bbox"][0], block["bbox"][1],
                    block["bbox"][2], block["bbox"][3],
                )
                if _in_table(block_bbox, tbl_bboxes):
                    continue  # text inside a table is already captured

                # Collect all spans across lines in this block
                all_spans = [
                    sp
                    for line in block.get("lines", [])
                    for sp in line.get("spans", [])
                ]
                rb = _spans_to_block(all_spans, page_h, page_num, block["bbox"][1])
                if rb:
                    doc.text_blocks.append(rb)

    return doc


# ---------------------------------------------------------------------------
# Font-size–based heading level classifier
# ---------------------------------------------------------------------------

def _classify_level(font_size: float, thresholds: dict) -> int:
    """Return heading level 1/2/3 or 0 (= paragraph) based on size thresholds."""
    if font_size >= thresholds["h1"]:
        return 1
    if font_size >= thresholds["h2"]:
        return 2
    if font_size >= thresholds["h3"]:
        return 3
    return 0


def _build_thresholds(blocks: List[RawTextBlock]) -> dict:
    sizes = sorted({b.font_size for b in blocks}, reverse=True)
    if not sizes:
        return {"h1": 9999, "h2": 9999, "h3": 9999}

    max_size = sizes[0]
    body_size = sizes[-1] if len(sizes) > 1 else max_size

    # Heading tiers: ≥80% of max, ≥65%, ≥55% — only if clearly above body
    def tier(pct: float) -> float:
        candidate = max_size * pct
        return candidate if candidate > body_size * 1.05 else 9999

    return {"h1": tier(0.80), "h2": tier(0.65), "h3": tier(0.55)}


# ---------------------------------------------------------------------------
# DocumentPlan builder (no LLM required)
# ---------------------------------------------------------------------------

def to_document_plan(doc: ParsedDocument) -> "DocumentPlan":
    """Converts ParsedDocument directly into a DocumentPlan without an LLM."""
    from .models import (
        DocumentPlan, PageSettings,
        HeadingBlock, ParagraphBlock, TableBlock,
    )

    thresholds = _build_thresholds(doc.text_blocks)

    # Build unified reading-order list: (page_num, y_ratio, item)
    items: list = []
    for tb in doc.text_blocks:
        items.append((tb.page_num, tb.y_ratio, "text", tb))
    for tbl in doc.tables:
        items.append((tbl.page_num, tbl.y_ratio, "table", tbl))
    items.sort(key=lambda x: (x[0], x[1]))

    blocks = []
    title = ""
    for _, _, kind, item in items:
        if kind == "text":
            level = _classify_level(item.font_size, thresholds)
            if level == 0 and item.is_bold:
                level = 3

            if level > 0:
                if not title and level == 1:
                    title = item.text
                blocks.append(HeadingBlock(content=item.text, level=level))
            else:
                blocks.append(ParagraphBlock(content=item.text))
        else:
            has_header = len(item.rows) > 1
            blocks.append(TableBlock(rows=item.rows, has_header=has_header))

    page = PageSettings(
        width_mm=round(doc.page_width_mm),
        height_mm=round(doc.page_height_mm),
    )
    return DocumentPlan(title=title, page=page, blocks=blocks)
