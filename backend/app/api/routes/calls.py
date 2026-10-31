import logging
from fastapi import APIRouter, HTTPException, WebSocket, Request, Response
from pydantic import BaseModel
from twilio.request_validator import RequestValidator

from backend.app.services.telephony import telephony_provider
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

class CallRequest(BaseModel):
    phone_number: str

async def verify_twilio_request(request: Request) -> bool:
    """
    Validates that the incoming HTTP request actually originated from Twilio.
    Returns True if valid or if verification is turned off in settings.
    """
    if not settings.VERIFY_TWILIO_SIGNATURE or not settings.TWILIO_AUTH_TOKEN:
        return True

    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        return False

    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    url = str(request.url)

    # For POST requests, include the form body
    if request.method == "POST":
        form_data = await request.form()
        params = dict(form_data)
    else:
        params = dict(request.query_params)

    return validator.validate(url, params, signature)

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
async def get_twiml(request: Request):
    """
    Returns TwiML to route the answered call to the Media Stream (WebSocket).
    """
    if not await verify_twilio_request(request):
        logger.warning("Rejected unverified request to /twiml")
        raise HTTPException(status_code=403, detail="Twilio signature verification failed.")

    if not settings.SERVER_DOMAIN:
        raise HTTPException(status_code=500, detail="SERVER_DOMAIN not configured.")

    clean_domain = settings.SERVER_DOMAIN.replace("https://", "").replace("http://", "").strip("/")
    ws_url = f"wss://{clean_domain}{settings.api_v1_str}/calls/media-stream"

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
