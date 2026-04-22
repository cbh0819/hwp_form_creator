"""FastAPI application – PDF → HWPX conversion with SSE progress tracking."""

import asyncio
import json
import tempfile
import uuid
from pathlib import Path
from typing import AsyncGenerator
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .pdf_parser import parse_pdf, to_document_plan
from .hwpx_generator import generate

app = FastAPI(
    title="HWP Form Creator",
    description="PDF를 업로드하면 유사한 구조의 HWP(X) 템플릿을 생성합니다.",
    version="0.4.0",
)

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# ---------------------------------------------------------------------------
# In-memory job store  {job_id: {status, progress, message, data, stem, error}}
# ---------------------------------------------------------------------------
_jobs: dict[str, dict] = {}


def _set(job_id: str, **kwargs) -> None:
    _jobs[job_id].update(kwargs)


async def _process(job_id: str, tmp_path: str, stem: str) -> None:
    try:
        _set(job_id, progress=15, status="running", message="PDF 파싱 중…")
        await asyncio.sleep(0)          # yield to event loop so SSE can flush
        parsed = parse_pdf(tmp_path)

        _set(job_id, progress=55, message="문서 구조 변환 중…")
        await asyncio.sleep(0)
        plan = to_document_plan(parsed)

        _set(job_id, progress=85, message="HWPX 파일 생성 중…")
        await asyncio.sleep(0)
        hwpx_bytes = generate(plan)

        _set(job_id, progress=100, status="done", message="완료", data=hwpx_bytes)
    except Exception as exc:
        _set(job_id, status="error", message="오류 발생", error=str(exc))
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/generate", summary="PDF 변환 시작 → job_id 반환")
async def start_generate(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="분석할 PDF 파일"),
) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 허용됩니다.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    job_id = str(uuid.uuid4())
    stem = Path(file.filename).stem
    _jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "message": "작업 시작 중…",
        "data": None,
        "stem": stem,
        "error": None,
    }

    background_tasks.add_task(_process, job_id, tmp_path, stem)
    return JSONResponse({"job_id": job_id})


@app.get("/progress/{job_id}", summary="SSE 진행도 스트림")
async def get_progress(job_id: str) -> StreamingResponse:
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="존재하지 않는 작업입니다.")

    async def event_stream() -> AsyncGenerator[str, None]:
        while True:
            job = _jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
                return

            payload: dict = {
                "progress": job["progress"],
                "status":   job["status"],
                "message":  job["message"],
            }
            if job["status"] == "error":
                payload["error"] = job["error"]

            yield f"data: {json.dumps(payload)}\n\n"

            if job["status"] in ("done", "error"):
                return

            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/download/{job_id}", summary="완료된 HWPX 파일 다운로드")
def download(job_id: str) -> Response:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="존재하지 않는 작업입니다.")
    if job["status"] == "error":
        raise HTTPException(status_code=500, detail=job["error"])
    if job["status"] != "done":
        raise HTTPException(status_code=202, detail="아직 처리 중입니다.")

    data = job["data"]
    stem = job["stem"]
    _jobs.pop(job_id, None)     # 다운로드 후 메모리 정리

    encoded = quote(stem + "_template.hwpx")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@app.post("/preview", summary="PDF 분석 결과 JSON 미리보기")
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
