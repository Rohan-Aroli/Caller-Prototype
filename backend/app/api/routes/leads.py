import io
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from starlette.concurrency import run_in_threadpool
from backend.app.schemas.leads import CsvProcessingResponse
from backend.app.services.csv_processor import process_csv
from backend.app.core.config import settings

router = APIRouter()

ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/csv",
    "text/x-csv",
    "application/x-csv",
}

@router.post("/upload-csv", response_model=CsvProcessingResponse)
async def upload_csv(
    file: UploadFile = File(...),
    agent_id: str = Form(...)
):
    if not agent_id.strip():
        raise HTTPException(status_code=400, detail="agent_id cannot be empty.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file.")

    is_csv_content_type = file.content_type in ALLOWED_CONTENT_TYPES
    is_csv_extension = file.filename.lower().endswith(".csv")

    if not is_csv_content_type and not is_csv_extension:
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    # Guard against memory exhaustion DoS by chunked read with max size check
    chunk_size = 1024 * 1024  # 1 MB chunk
    chunks = []
    total_bytes = 0
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > settings.max_upload_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size of {settings.max_upload_size_bytes // (1024 * 1024)}MB."
            )
        chunks.append(chunk)

    if not chunks or total_bytes == 0:
        raise HTTPException(status_code=400, detail="File is empty.")

    content = b"".join(chunks)

    # Use BytesIO and TextIOWrapper with utf-8-sig to decode on-the-fly and handle BOM
    file_obj = io.TextIOWrapper(io.BytesIO(content), encoding="utf-8-sig")

    # Run CPU-bound CSV processing in worker thread pool so asyncio event loop is not blocked
    return await run_in_threadpool(process_csv, file_obj, agent_id)
