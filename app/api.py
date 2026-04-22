"""FastAPI application exposing the PDF → HWPX conversion service."""

import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from .pdf_parser import parse_pdf, to_prompt_text
from .llm_analyzer import analyze
from .hwpx_generator import generate

app = FastAPI(
    title="HWP Form Creator",
    description="PDF를 업로드하면 유사한 구조의 HWP(X) 템플릿을 생성합니다.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/generate",
    summary="PDF → HWPX 변환",
    response_description="생성된 .hwpx 파일 (application/octet-stream)",
)
async def generate_hwpx(
    file: UploadFile = File(..., description="분석할 PDF 파일"),
    api_key: Optional[str] = Form(
        default=None,
        description="Anthropic API 키 (환경변수 ANTHROPIC_API_KEY로 대체 가능)",
    ),
) -> Response:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 허용됩니다.")

    effective_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not effective_key:
        raise HTTPException(
            status_code=422,
            detail="ANTHROPIC_API_KEY 환경변수 또는 api_key 파라미터가 필요합니다.",
        )

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        parsed = parse_pdf(tmp_path)
        prompt_text = to_prompt_text(parsed)
        plan = analyze(prompt_text, api_key=effective_key)
        hwpx_bytes = generate(plan)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    stem = Path(file.filename).stem
    return Response(
        content=hwpx_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{stem}_template.hwpx"'},
    )


@app.post(
    "/preview",
    summary="PDF 분석 결과 미리보기 (JSON)",
    response_description="Claude가 분석한 문서 구조 JSON",
)
async def preview(
    file: UploadFile = File(..., description="분석할 PDF 파일"),
    api_key: Optional[str] = Form(default=None),
) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 허용됩니다.")

    effective_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not effective_key:
        raise HTTPException(
            status_code=422,
            detail="ANTHROPIC_API_KEY 환경변수 또는 api_key 파라미터가 필요합니다.",
        )

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        parsed = parse_pdf(tmp_path)
        prompt_text = to_prompt_text(parsed)
        plan = analyze(prompt_text, api_key=effective_key)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return JSONResponse(content=plan.model_dump())
