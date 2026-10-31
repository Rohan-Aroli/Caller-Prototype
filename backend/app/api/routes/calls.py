from fastapi import APIRouter, HTTPException, WebSocket, Request, Response
from pydantic import BaseModel
import logging

from backend.app.services.telephony import telephony_provider
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

class CallRequest(BaseModel):
    phone_number: str

@router.post("/trigger-call")
async def trigger_call(request: CallRequest):
    """
    Initiate an outbound call to the provided phone number.
    """
    try:
        call_sid = telephony_provider.trigger_call(request.phone_number)
        return {"status": "success", "call_sid": call_sid}
    except Exception as e:
        logger.error(f"Failed to trigger call: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/twiml")
@router.get("/twiml")
async def get_twiml():
    """
    Returns TwiML to route the answered call to the Media Stream (WebSocket).
    """
    if not settings.SERVER_DOMAIN:
        raise HTTPException(status_code=500, detail="SERVER_DOMAIN not configured.")

    # Twilio needs wss:// for WebSockets
    ws_url = f"wss://{settings.SERVER_DOMAIN}{settings.api_v1_str}/calls/media-stream"

    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""

    return Response(content=twiml_response, media_type="application/xml")

@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Stream.
    """
    await telephony_provider.handle_media_stream(websocket)
