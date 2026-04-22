"""FastAPI application exposing the PDF → HWPX conversion service."""

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from .pdf_parser import parse_pdf, to_document_plan
from .hwpx_generator import generate

app = FastAPI(
    title="HWP Form Creator",
    description="PDF를 업로드하면 유사한 구조의 HWP(X) 템플릿을 생성합니다.",
    version="0.2.0",
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
) -> Response:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 허용됩니다.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        parsed = parse_pdf(tmp_path)
        plan = to_document_plan(parsed)
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
    response_description="파싱된 문서 구조 JSON",
)
async def preview(
    file: UploadFile = File(..., description="분석할 PDF 파일"),
) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 허용됩니다.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        parsed = parse_pdf(tmp_path)
        plan = to_document_plan(parsed)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return JSONResponse(content=plan.model_dump())
