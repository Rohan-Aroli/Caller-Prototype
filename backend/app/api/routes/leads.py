import io
import uuid
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from backend.app.schemas.leads import CsvProcessingResponse, AcceptedLead, LeadRecord
from backend.app.services.csv_processor import process_csv, parse_leads_csv, save_evaluated_leads_csv, normalize_header
from backend.app.services.call_state import call_state_manager
from backend.app.services.telephony import telephony_provider
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/csv",
    "text/x-csv",
    "application/x-csv",
    "application/octet-stream",
}

async def trigger_single_lead_call(lead: LeadRecord):
    """
    Background worker that triggers the initial outbound call for a lead.
    """
    try:
        call_sid = telephony_provider.trigger_call(to_number=lead.number, lead_id=lead.id)
        await call_state_manager.bind_call_sid(lead.id, call_sid)
        lead.status = "initiated"
        await call_state_manager.update_lead(lead)
        logger.info(f"Outbound call initiated for {lead.name} ({lead.number}), call_sid={call_sid}")
    except Exception as e:
        logger.error(f"Failed to initiate call for lead {lead.name} ({lead.number}): {e}")
        lead.status = "failed"
        lead.evaluation_notes = f"Initial dispatch failed: {e}"
        await call_state_manager.update_lead(lead)
        leads = await call_state_manager.get_leads_by_batch(lead.batch_id)
        if leads:
            save_evaluated_leads_csv(lead.batch_id, leads)

@router.post("/upload-csv", response_model=CsvProcessingResponse)
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    agent_id: str = Form(...)
):
    """
    Ingests lead CSV file:
    1. If a 3-column calling format ('name', 'number', 'reason for calling') is detected:
       - Strictly validates each row (rejecting with HTTP 422 if missing fields or invalid phone).
       - Registers leads in LeadSessionManager.
       - Dispatches outbound calls in the background.
       - Initializes evaluated CSV output.
    2. Otherwise, processes in standard lead validation mode for backward compatibility.
    """
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

    # Peek at headers to decide processing strategy
    try:
        decoded_preview = content[:2048].decode("utf-8-sig", errors="replace")
    except Exception:
        decoded_preview = ""

    header_line = ""
    for line in decoded_preview.splitlines():
        if line.strip():
            header_line = line
            break

    raw_headers = [h.strip().lower().replace(" ", "_") for h in header_line.split(",")]
    is_calling_lead_csv = any(
        h in ("reason_for_calling", "reason", "reason_for_call", "campaign_objective")
        for h in raw_headers
    ) or ("number" in raw_headers and "phone" not in raw_headers)

    if is_calling_lead_csv:
        # Strict 3-column outbound campaign parsing
        file_obj = io.TextIOWrapper(io.BytesIO(content), encoding="utf-8-sig")
        batch_id = str(uuid.uuid4())
        leads = parse_leads_csv(file_obj, batch_id=batch_id)

        # Register all leads in memory state manager
        for lead in leads:
            await call_state_manager.register_lead(lead)

        # Write initial processed CSV record
        save_evaluated_leads_csv(batch_id, leads)

        # Queue outbound calls for all leads
        for lead in leads:
            background_tasks.add_task(trigger_single_lead_call, lead)

        accepted_leads = [
            AcceptedLead(
                row_number=i + 2,
                name=l.name,
                phone=l.number,
                extra_fields={"reason_for_calling": l.reason_for_calling},
                assigned_agent_id=agent_id
            )
            for i, l in enumerate(leads)
        ]

        return CsvProcessingResponse(
            status="processed",
            agent_id=agent_id,
            total_rows=len(leads),
            accepted_count=len(leads),
            rejected_count=0,
            accepted_leads=accepted_leads,
            rejected_rows=[],
            batch_id=batch_id,
            download_url=f"/api/v1/leads/download-results/{batch_id}",
            leads=leads
        )
    else:
        # Standard legacy processing
        file_obj = io.TextIOWrapper(io.BytesIO(content), encoding="utf-8-sig")
        return await run_in_threadpool(process_csv, file_obj, agent_id)

@router.get("/download-results/{batch_id}")
async def download_results(batch_id: str):
    """
    Downloads the evaluated leads CSV containing conversation scores,
    sentiment evaluation notes, retry counts, and call status.
    """
    output_dir = Path(settings.PROCESSED_CSV_DIR)
    target_path = output_dir / f"leads_evaluated_{batch_id}.csv"

    if not target_path.exists():
        # Check if batch exists in memory and regenerate CSV
        leads = await call_state_manager.get_leads_by_batch(batch_id)
        if leads:
            target_path = save_evaluated_leads_csv(batch_id, leads)
        else:
            raise HTTPException(status_code=404, detail=f"No results found for batch '{batch_id}'.")

    return FileResponse(
        path=str(target_path),
        media_type="text/csv",
        filename=f"leads_evaluated_{batch_id}.csv"
    )
