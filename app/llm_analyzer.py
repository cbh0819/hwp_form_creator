"""Uses Claude API to convert raw PDF content into a structured DocumentPlan."""

import json
import os
from typing import Optional

import anthropic

from .models import (
    DocumentPlan,
    HeadingBlock,
    ParagraphBlock,
    TableBlock,
    PageSettings,
)

_SYSTEM_PROMPT = """당신은 PDF 문서를 분석하여 한글(HWP) 문서 구조를 설계하는 전문가입니다.
사용자가 제공하는 PDF 내용을 분석하고, 해당 문서와 유사한 형태의 HWP 템플릿 구조를 JSON으로 반환하세요.

반드시 아래 JSON 스키마를 정확히 따르세요:
{
  "title": "문서 제목",
  "page": {
    "width_mm": 210,
    "height_mm": 297,
    "margin_left_mm": 30,
    "margin_right_mm": 30,
    "margin_top_mm": 20,
    "margin_bottom_mm": 15
  },
  "blocks": [
    {"type": "heading", "content": "제목 텍스트", "level": 1, "align": "center"},
    {"type": "paragraph", "content": "본문 내용", "align": "justify", "bold": false},
    {
      "type": "table",
      "has_header": true,
      "rows": [
        ["헤더1", "헤더2", "헤더3"],
        ["값1",   "값2",   "값3"]
      ]
    }
  ]
}

규칙:
- heading level: 1(대제목), 2(중제목), 3(소제목)
- align: "left" | "center" | "right" | "justify"
- 표는 원본 PDF의 표 구조를 최대한 반영하되, 실제 데이터 대신 적절한 샘플/플레이스홀더를 사용하세요
- 본문이 긴 경우 대표 단락 3~5개로 압축하세요
- JSON 외 다른 텍스트는 절대 포함하지 마세요"""

_USER_PROMPT_TEMPLATE = """아래 PDF 문서 내용을 분석하여 HWP 템플릿 구조 JSON을 생성해 주세요.

{content}

위 내용을 참고하여 동일한 레이아웃·구조의 HWP 문서 템플릿을 JSON으로 반환하세요."""


def analyze(pdf_text: str, api_key: Optional[str] = None) -> DocumentPlan:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=key)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": _USER_PROMPT_TEMPLATE.format(content=pdf_text[:12000]),
            }
        ],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    data = json.loads(raw)
    return _parse_plan(data)


def _parse_plan(data: dict) -> DocumentPlan:
    page_data = data.get("page", {})
    page = PageSettings(
        width_mm=int(page_data.get("width_mm", 210)),
        height_mm=int(page_data.get("height_mm", 297)),
        margin_left_mm=int(page_data.get("margin_left_mm", 30)),
        margin_right_mm=int(page_data.get("margin_right_mm", 30)),
        margin_top_mm=int(page_data.get("margin_top_mm", 20)),
        margin_bottom_mm=int(page_data.get("margin_bottom_mm", 15)),
    )

    blocks = []
    for b in data.get("blocks", []):
        btype = b.get("type")
        if btype == "heading":
            blocks.append(
                HeadingBlock(
                    content=str(b.get("content", "")),
                    level=int(b.get("level", 1)),
                    align=b.get("align", "left"),
                )
            )
        elif btype == "table":
            rows = [[str(c) for c in row] for row in b.get("rows", [])]
            blocks.append(TableBlock(rows=rows, has_header=bool(b.get("has_header", False))))
        else:
            blocks.append(
                ParagraphBlock(
                    content=str(b.get("content", "")),
                    align=b.get("align", "justify"),
                    bold=bool(b.get("bold", False)),
                )
            )

    return DocumentPlan(title=str(data.get("title", "")), page=page, blocks=blocks)
