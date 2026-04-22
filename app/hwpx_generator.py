"""Generates .hwpx files (HWP Open XML format) from a DocumentPlan.

HWPX is a ZIP archive with this layout:
  mimetype
  META-INF/container.xml
  Contents/content.hpf        ← package descriptor
  Contents/header.xml         ← fonts, styles, page layout
  Contents/section0.xml       ← document body
"""

import io
import zipfile
from typing import List

from .models import DocumentPlan, HeadingBlock, ParagraphBlock, TableBlock

# ---------------------------------------------------------------------------
# HWP unit helpers  (1 HWP unit = 1/7200 inch)
# ---------------------------------------------------------------------------
_MM_TO_HWP = 7200 / 25.4  # ≈ 283.46 units per mm


def _mm(mm: float) -> int:
    return round(mm * _MM_TO_HWP)


# ---------------------------------------------------------------------------
# Static file content
# ---------------------------------------------------------------------------

_MIMETYPE = "application/hwp+zip"

_CONTAINER_XML = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<container>
  <rootfiles>
    <rootfile full-path="Contents/content.hpf" media-type="application/hwp+zip"/>
  </rootfiles>
</container>"""

_CONTENT_HPF = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<opf:package xmlns:opf="http://www.idpf.org/2007/opf"
             xmlns:dc="http://purl.org/dc/elements/1.1/"
             version="2.0" unique-identifier="BookId">
  <opf:metadata>
    <dc:title>{title}</dc:title>
    <dc:language>ko</dc:language>
  </opf:metadata>
  <opf:manifest>
    <opf:item id="header"   href="header.xml"   media-type="application/xml"/>
    <opf:item id="section0" href="section0.xml" media-type="application/xml"/>
  </opf:manifest>
  <opf:spine>
    <opf:itemref idref="section0"/>
  </opf:spine>
</opf:package>"""

# ---------------------------------------------------------------------------
# Header XML builder
# ---------------------------------------------------------------------------

# Character property IDs
_CP_NORMAL = 0   # 10pt, normal
_CP_H1 = 1       # 16pt, bold
_CP_H2 = 2       # 13pt, bold
_CP_H3 = 3       # 11pt, bold
_CP_BOLD = 4     # 10pt, bold

# Paragraph property IDs
_PP_NORMAL = 0
_PP_H1 = 1
_PP_H2 = 2
_PP_H3 = 3

# Border fill IDs
_BF_NONE = 0
_BF_TABLE = 1


def _border_fill(bid: int, border_type: str = "NONE", width: str = "0.1mm") -> str:
    def border(pos: str) -> str:
        return f'<hh:{pos}Border type="{border_type}" width="{width}" color="0"/>'

    return f"""\
      <hh:borderFill id="{bid}" threeD="0" shadow="0" centerLine="0" breakCellSeparateLine="0">
        <hh:slash type="NONE" Crooked="0" isCounter="0"/>
        <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
        {border("left")}
        {border("right")}
        {border("top")}
        {border("bottom")}
        <hh:diagonal type="NONE" width="0.1mm" color="0"/>
        <hh:fillBrush><hh:windowBrush/></hh:fillBrush>
      </hh:borderFill>"""


def _char_prop(cid: int, size_pt: int, bold: int = 0) -> str:
    size = size_pt * 100
    return (
        f'      <hh:charProperty id="{cid}" height="{size}" textColor="0" shadeColor="-1" '
        f'bold="{bold}" italic="0" underline="0" strikeOut="0" '
        f'outline="0" shadow="0" emboss="0" engrave="0" '
        f'superscript="0" subscript="0" '
        f'shadowColor="0" shadowX="0" shadowY="0" '
        f'underlineColor="0" underlineShape="SOLID" '
        f'strikeColor="0" strikeShape="SOLID" '
        f'fontRef="0" langRef="0" hintRef="0" '
        f'ratioX="100" ratioY="100" spacing="0" '
        f'borderFillIDRef="0"/>'
    )


def _para_prop(pid: int, align: str = "JUSTIFY",
               space_before: int = 0, space_after: int = 0,
               line_spacing: int = 160) -> str:
    return f"""\
      <hh:paraProperty id="{pid}" align="{align}" headingType="NONE" level="0"
                       tabIDRef="0" numberingIDRef="0" pageBreakBefore="0"
                       lineWrap="BREAK" verticalAlign="BASELINE"
                       linkListIDRef="0" linkListNextIDRef="0"
                       instantIndentOnNumbering="0" suppressLineNumbers="0">
        <hh:paraMargin left="0" right="0" prev="{space_before}" next="{space_after}" indent="0"/>
        <hh:paraLineSpace type="RATIO" value="{line_spacing}"/>
        <hh:paraBorder borderFillIDRef="0" offsetLeft="0" offsetRight="0"
                       offsetTop="0" offsetBottom="0" connect="0" ignoreMargin="0"/>
        <hh:paraShading borderFillIDRef="0"/>
      </hh:paraProperty>"""


def _build_header_xml(plan: DocumentPlan) -> str:
    p = plan.page
    page_w = _mm(p.width_mm)
    page_h = _mm(p.height_mm)
    m_l = _mm(p.margin_left_mm)
    m_r = _mm(p.margin_right_mm)
    m_t = _mm(p.margin_top_mm)
    m_b = _mm(p.margin_bottom_mm)
    header_len = _mm(10)
    footer_len = _mm(10)

    return f"""\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2012/head">
  <hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" eq="1"/>
  <hh:refList>

    <hh:fontFaces>
      <hh:fontFace lang="HANGUL">
        <hh:font id="0" face="함초롬바탕" type="TTF" isEmbedded="0"/>
      </hh:fontFace>
      <hh:fontFace lang="LATIN">
        <hh:font id="0" face="Times New Roman" type="TTF" isEmbedded="0"/>
      </hh:fontFace>
      <hh:fontFace lang="HANJA">
        <hh:font id="0" face="함초롬바탕" type="TTF" isEmbedded="0"/>
      </hh:fontFace>
      <hh:fontFace lang="JAPANESE">
        <hh:font id="0" face="함초롬바탕" type="TTF" isEmbedded="0"/>
      </hh:fontFace>
      <hh:fontFace lang="OTHER">
        <hh:font id="0" face="함초롬바탕" type="TTF" isEmbedded="0"/>
      </hh:fontFace>
      <hh:fontFace lang="SYMBOL">
        <hh:font id="0" face="Symbol" type="TTF" isEmbedded="0"/>
      </hh:fontFace>
      <hh:fontFace lang="USER">
        <hh:font id="0" face="함초롬바탕" type="TTF" isEmbedded="0"/>
      </hh:fontFace>
    </hh:fontFaces>

    <hh:borderFills>
{_border_fill(_BF_NONE, "NONE")}
{_border_fill(_BF_TABLE, "SOLID", "0.12mm")}
    </hh:borderFills>

    <hh:charProperties>
{_char_prop(_CP_NORMAL, 10, 0)}
{_char_prop(_CP_H1,     16, 1)}
{_char_prop(_CP_H2,     13, 1)}
{_char_prop(_CP_H3,     11, 1)}
{_char_prop(_CP_BOLD,   10, 1)}
    </hh:charProperties>

    <hh:tabProperties>
      <hh:tabProperty id="0" autoTabLeft="0" autoTabRight="0">
        <hh:tabDef/>
      </hh:tabProperty>
    </hh:tabProperties>

    <hh:numberingProperties>
      <hh:numberingProperty id="0"/>
    </hh:numberingProperties>

    <hh:paraProperties>
{_para_prop(_PP_NORMAL, "JUSTIFY",   0,   0, 160)}
{_para_prop(_PP_H1,     "CENTER",  300, 200, 140)}
{_para_prop(_PP_H2,     "LEFT",    200, 100, 150)}
{_para_prop(_PP_H3,     "LEFT",    100,  50, 150)}
    </hh:paraProperties>

    <hh:styles>
      <hh:style id="0" type="PARA" name="바탕글"    engName="Normal"   paraPrIDRef="{_PP_NORMAL}" charPrIDRef="{_CP_NORMAL}" nextStyleIDRef="0" langIDRef="0" lockForm="0"/>
      <hh:style id="1" type="PARA" name="제목 1"    engName="Heading1" paraPrIDRef="{_PP_H1}"     charPrIDRef="{_CP_H1}"     nextStyleIDRef="0" langIDRef="0" lockForm="0"/>
      <hh:style id="2" type="PARA" name="제목 2"    engName="Heading2" paraPrIDRef="{_PP_H2}"     charPrIDRef="{_CP_H2}"     nextStyleIDRef="0" langIDRef="0" lockForm="0"/>
      <hh:style id="3" type="PARA" name="제목 3"    engName="Heading3" paraPrIDRef="{_PP_H3}"     charPrIDRef="{_CP_H3}"     nextStyleIDRef="0" langIDRef="0" lockForm="0"/>
    </hh:styles>

    <hh:masterPages>
      <hh:masterPage id="0"
                     width="{page_w}" height="{page_h}"
                     leftMargin="{m_l}" rightMargin="{m_r}"
                     topMargin="{m_t}" bottomMargin="{m_b}"
                     headerLen="{header_len}" footerLen="{footer_len}"
                     gutterLen="0" gutterType="LEFT_ONLY"
                     bindingDirection="LEFT" landscape="0"/>
    </hh:masterPages>

    <hh:trackChanges/>
  </hh:refList>
</hh:head>"""


# ---------------------------------------------------------------------------
# Section XML builder
# ---------------------------------------------------------------------------

_PARA_ID = 0  # global paragraph ID counter (reset per document)


def _next_id() -> int:
    global _PARA_ID
    _PARA_ID += 1
    return _PARA_ID


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


def _para(text: str, para_pr: int, char_pr: int) -> str:
    pid = _next_id()
    rid = _next_id()
    escaped = _xml_escape(text)
    return f"""\
  <hp:p id="{pid}">
    <hp:pPr id="{_next_id()}">
      <hp:pStyle paraPrIDRef="{para_pr}" charPrIDRef="{char_pr}"
                 nextParaIDRef="0" tabIDRef="0" numberingIDRef="0"
                 pageBreak="0" columnBreak="0" fontRef="0" langRef="0"/>
    </hp:pPr>
    <hp:run id="{rid}">
      <hp:rPr charPrIDRef="{char_pr}"/>
      <hp:t>{escaped}</hp:t>
    </hp:run>
  </hp:p>"""


def _empty_para() -> str:
    """A blank paragraph (spacer)."""
    pid = _next_id()
    return f"""\
  <hp:p id="{pid}">
    <hp:pPr id="{_next_id()}">
      <hp:pStyle paraPrIDRef="{_PP_NORMAL}" charPrIDRef="{_CP_NORMAL}"
                 nextParaIDRef="0" tabIDRef="0" numberingIDRef="0"
                 pageBreak="0" columnBreak="0" fontRef="0" langRef="0"/>
    </hp:pPr>
    <hp:run id="{_next_id()}">
      <hp:rPr charPrIDRef="{_CP_NORMAL}"/>
      <hp:t/>
    </hp:run>
  </hp:p>"""


def _table_xml(block: TableBlock, page: "PageSettings") -> str:
    """Builds a <hp:tbl> element for the given TableBlock."""
    if not block.rows:
        return ""

    num_cols = max(len(r) for r in block.rows)
    num_rows = len(block.rows)

    usable_width_mm = page.width_mm - page.margin_left_mm - page.margin_right_mm
    usable_width = _mm(usable_width_mm)
    col_width = usable_width // num_cols if num_cols else usable_width
    row_height = _mm(6)

    cell_margin_h = 360   # ≈ 1.27mm
    cell_margin_v = 141   # ≈ 0.5mm

    tbl_id = _next_id()
    rows_xml: List[str] = []

    for r_idx, row in enumerate(block.rows):
        cells_xml: List[str] = []
        for c_idx in range(num_cols):
            cell_text = row[c_idx] if c_idx < len(row) else ""
            char_pr = _CP_BOLD if (block.has_header and r_idx == 0) else _CP_NORMAL
            cell_pid = _next_id()
            cell_rid = _next_id()
            escaped = _xml_escape(cell_text)

            cells_xml.append(f"""\
      <hp:tc>
        <hp:tcPr>
          <hp:cellAddr row="{r_idx}" col="{c_idx}"/>
          <hp:cellSpan rowSpan="1" colSpan="1"/>
          <hp:cellSz width="{col_width}" height="{row_height}"/>
          <hp:cellMargin left="{cell_margin_h}" right="{cell_margin_h}"
                         top="{cell_margin_v}" bottom="{cell_margin_v}"/>
          <hp:borderFill borderFillIDRef="{_BF_TABLE}"/>
        </hp:tcPr>
        <hp:subList>
          <hp:p id="{cell_pid}">
            <hp:pPr id="{_next_id()}">
              <hp:pStyle paraPrIDRef="{_PP_NORMAL}" charPrIDRef="{char_pr}"
                         nextParaIDRef="0" tabIDRef="0" numberingIDRef="0"
                         pageBreak="0" columnBreak="0" fontRef="0" langRef="0"/>
            </hp:pPr>
            <hp:run id="{cell_rid}">
              <hp:rPr charPrIDRef="{char_pr}"/>
              <hp:t>{escaped}</hp:t>
            </hp:run>
          </hp:p>
        </hp:subList>
      </hp:tc>""")

        rows_xml.append(
            f'    <hp:tr>\n' + "\n".join(cells_xml) + "\n    </hp:tr>"
        )

    rows_str = "\n".join(rows_xml)
    return f"""\
  <hp:tbl id="{tbl_id}" zOrder="0" numberingType="NONE"
          textWrap="SQUARE" textFlow="BOTH" treatAsChar="0"
          lineWrap="AROUND" page="0" column="0"
          width="TABLE" widthValue="{usable_width}" height="0"
          marginLeft="0" marginRight="0" marginTop="0" marginBottom="0"
          borderFillIDRef="{_BF_TABLE}"
          cellSpacing="0" leftInnerMargin="{cell_margin_h}"
          rightInnerMargin="{cell_margin_h}" topInnerMargin="{cell_margin_v}"
          bottomInnerMargin="{cell_margin_v}"
          numCols="{num_cols}" numRows="{num_rows}">
{rows_str}
  </hp:tbl>"""


def _build_section_xml(plan: DocumentPlan) -> str:
    global _PARA_ID
    _PARA_ID = 0

    parts: List[str] = []

    for block in plan.blocks:
        if isinstance(block, HeadingBlock):
            level_map = {1: (_PP_H1, _CP_H1), 2: (_PP_H2, _CP_H2), 3: (_PP_H3, _CP_H3)}
            pp, cp = level_map.get(block.level, (_PP_H2, _CP_H2))
            parts.append(_para(block.content, pp, cp))
            parts.append(_empty_para())

        elif isinstance(block, ParagraphBlock):
            cp = _CP_BOLD if block.bold else _CP_NORMAL
            parts.append(_para(block.content, _PP_NORMAL, cp))

        elif isinstance(block, TableBlock):
            parts.append(_empty_para())
            tbl = _table_xml(block, plan.page)
            if tbl:
                parts.append(tbl)
            parts.append(_empty_para())

    # Ensure at least one paragraph
    if not parts:
        parts.append(_empty_para())

    body = "\n".join(parts)
    return f"""\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2012/section"
        xmlns:hp="http://www.hancom.co.kr/hwpml/2012/paragraph"
        id="0">
{body}
</hs:sec>"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(plan: DocumentPlan) -> bytes:
    """Returns the raw bytes of a .hwpx file for the given DocumentPlan."""
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be the first entry and stored (not compressed)
        zf.writestr(
            zipfile.ZipInfo("mimetype"),
            _MIMETYPE,
        )
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr(
            "Contents/content.hpf",
            _CONTENT_HPF.format(title=_xml_escape(plan.title)),
        )
        zf.writestr("Contents/header.xml", _build_header_xml(plan))
        zf.writestr("Contents/section0.xml", _build_section_xml(plan))

    return buf.getvalue()
