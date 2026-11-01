import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, WebSocket, Request, Response, BackgroundTasks
from pydantic import BaseModel
from twilio.request_validator import RequestValidator

from backend.app.services.telephony import telephony_provider
from backend.app.services.call_state import call_state_manager
from backend.app.services.csv_processor import save_evaluated_leads_csv
from backend.app.schemas.leads import LeadRecord
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

class CallRequest(BaseModel):
    phone_number: str

async def verify_twilio_request(request: Request) -> bool:
    """
    Validates that the incoming HTTP request actually originated from Twilio.
    Returns True if valid or if verification is turned off in settings.
    Properly handles public reverse proxy domains (e.g. ngrok).
    """
    if not settings.VERIFY_TWILIO_SIGNATURE or not settings.TWILIO_AUTH_TOKEN:
        return True

    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        logger.warning("Missing X-Twilio-Signature header on webhook request.")
        return False

    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)

    # If behind a public reverse proxy (e.g. ngrok), Twilio signed the public URL
    if settings.SERVER_DOMAIN:
        clean_domain = settings.SERVER_DOMAIN.replace("https://", "").replace("http://", "").strip("/")
        url = f"https://{clean_domain}{request.url.path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"
    else:
        url = str(request.url)

    # For POST requests, include the form body
    if request.method == "POST":
        form_data = await request.form()
        params = dict(form_data)
    else:
        params = dict(request.query_params)

    is_valid = validator.validate(url, params, signature)
    if not is_valid:
        logger.warning(f"Twilio signature validation failed for URL: {url}")
    return is_valid

async def scheduled_retry_call(lead: LeadRecord, delay_seconds: int):
    """
    Wait for delay_seconds and re-trigger an outbound call for an unanswered lead.
    """
    logger.info(f"Waiting {delay_seconds}s before retrying call for lead {lead.name} ({lead.number}) [Retry {lead.retry_count}]...")
    await asyncio.sleep(delay_seconds)
    try:
        new_call_sid = telephony_provider.trigger_call(lead.number, lead_id=lead.id)
        await call_state_manager.bind_call_sid(lead.id, new_call_sid)
        lead.status = "in_progress"
        await call_state_manager.update_lead(lead)
        logger.info(f"Retry call successfully triggered for {lead.name}, call_sid={new_call_sid}")
    except Exception as e:
        logger.error(f"Error triggering retry call for lead {lead.name}: {e}")
        lead.status = "unreachable"
        lead.evaluation_notes = f"Retry attempt failed: {e}"
        await call_state_manager.update_lead(lead)
        leads = await call_state_manager.get_leads_by_batch(lead.batch_id)
        if leads:
            save_evaluated_leads_csv(lead.batch_id, leads)

async def evaluate_and_persist_lead(lead: LeadRecord, session_key: str):
    """
    Run Gemini post-call transcript evaluation and update CSV.
    """
    try:
        transcript = await call_state_manager.get_transcript(session_key)
        await telephony_provider.evaluate_lead_transcript(lead, transcript)
        leads = await call_state_manager.get_leads_by_batch(lead.batch_id)
        if leads:
            save_evaluated_leads_csv(lead.batch_id, leads)
    except Exception as e:
        logger.error(f"Error evaluating and persisting lead {lead.name}: {e}")

@router.post("/trigger-call")
async def trigger_call(request: CallRequest):
    """
    Initiate an outbound call to the provided phone number.
    """
    try:
        call_sid = telephony_provider.trigger_call(request.phone_number)
        return {"status": "success", "call_sid": call_sid}
    except ValueError as e:
        logger.warning(f"Configuration or validation error triggering call: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to trigger call: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/twiml")
@router.get("/twiml")
async def get_twiml(request: Request, lead_id: Optional[str] = None):
    """
    Returns TwiML to route the answered call to the Media Stream (WebSocket).
    """
    if not await verify_twilio_request(request):
        logger.warning("Rejected unverified request to /twiml")
        raise HTTPException(status_code=403, detail="Twilio signature verification failed.")

    if not settings.SERVER_DOMAIN:
        raise HTTPException(status_code=500, detail="SERVER_DOMAIN not configured.")

    clean_domain = settings.SERVER_DOMAIN.replace("https://", "").replace("http://", "").strip("/")
    lead_param = f"?lead_id={lead_id}" if lead_id else ""
    ws_url = f"wss://{clean_domain}{settings.api_v1_str}/calls/media-stream{lead_param}"

    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""

    return Response(content=twiml_response, media_type="application/xml")

@router.post("/status-callback")
async def status_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    lead_id: Optional[str] = None
):
    """
    Twilio Call Status Callback handler:
    1. Tracks call lifecycle events ('initiated', 'ringing', 'answered', 'completed', 'busy', 'no-answer', 'failed', 'canceled').
    2. Executes automatic retry for unanswered calls up to CALL_MAX_RETRIES after CALL_RETRY_DELAY_SECONDS.
    3. Runs post-call LLM evaluation on call completion.
    """
    if not await verify_twilio_request(request):
        logger.warning("Rejected unverified request to /status-callback")
        raise HTTPException(status_code=403, detail="Twilio signature verification failed.")

    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    call_status = form_data.get("CallStatus", "").lower()

    logger.info(f"Received Twilio status callback for CallSid={call_sid}, status={call_status}, lead_id={lead_id}")

    # Resolve LeadRecord
    lead: Optional[LeadRecord] = None
    if lead_id:
        lead = await call_state_manager.get_lead_by_id(lead_id)
    if not lead and call_sid:
        lead = await call_state_manager.get_lead_by_call_sid(call_sid)

    if not lead:
        logger.debug(f"No lead associated with CallSid {call_sid} (likely direct/test call).")
        return {"status": "ignored", "reason": "lead_not_tracked"}

    # Handle unanswered / failed call states
    if call_status in ("busy", "no-answer", "failed", "canceled"):
        if lead.retry_count < settings.CALL_MAX_RETRIES:
            lead.retry_count += 1
            lead.status = "retry_pending"
            await call_state_manager.update_lead(lead)
            logger.info(f"Scheduling retry #{lead.retry_count} for lead {lead.name} in {settings.CALL_RETRY_DELAY_SECONDS}s")
            background_tasks.add_task(
                scheduled_retry_call,
                lead=lead,
                delay_seconds=settings.CALL_RETRY_DELAY_SECONDS
            )
        else:
            lead.status = "unreachable"
            lead.investment_score = 0
            lead.interest_level = "None"
            lead.evaluation_notes = f"Call terminated with status: {call_status}. Max retries ({settings.CALL_MAX_RETRIES}) reached."
            await call_state_manager.update_lead(lead)
            leads = await call_state_manager.get_leads_by_batch(lead.batch_id)
            if leads:
                save_evaluated_leads_csv(lead.batch_id, leads)

    elif call_status == "completed":
        # Call completed: evaluate transcript and update CSV
        session_key = call_sid or lead.id
        background_tasks.add_task(evaluate_and_persist_lead, lead=lead, session_key=session_key)

    elif call_status in ("in-progress", "answered"):
        lead.status = "answered"
        await call_state_manager.update_lead(lead)

    return {"status": "received", "lead_id": lead.id, "call_status": call_status}

@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket, lead_id: Optional[str] = None):
    """
    WebSocket endpoint for Twilio Media Stream.
    """
    await telephony_provider.handle_media_stream(websocket, lead_id=lead_id)
