from typing import List, Optional, Literal, Union, Annotated
from pydantic import BaseModel, Field


class HeadingBlock(BaseModel):
    type: Literal["heading"] = "heading"
    content: str
    level: int = Field(default=1, ge=1, le=3)
    align: Literal["left", "center", "right", "justify"] = "left"


class ParagraphBlock(BaseModel):
    type: Literal["paragraph"] = "paragraph"
    content: str
    align: Literal["left", "center", "right", "justify"] = "justify"
    bold: bool = False


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    rows: List[List[str]]
    has_header: bool = False


DocumentBlock = Annotated[
    Union[HeadingBlock, ParagraphBlock, TableBlock],
    Field(discriminator="type"),
]


class PageSettings(BaseModel):
    width_mm: int = 210
    height_mm: int = 297
    margin_left_mm: int = 30
    margin_right_mm: int = 30
    margin_top_mm: int = 20
    margin_bottom_mm: int = 15


class DocumentPlan(BaseModel):
    title: str = ""
    page: PageSettings = Field(default_factory=PageSettings)
    blocks: List[Union[HeadingBlock, ParagraphBlock, TableBlock]] = Field(default_factory=list)
