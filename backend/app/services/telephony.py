import json
import base64
import asyncio
import logging
from typing import Optional, List, Dict
from twilio.rest import Client
from fastapi import WebSocket, WebSocketDisconnect
import httpx
import google.generativeai as genai
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types.listen_v1results import ListenV1Results

from backend.app.core.config import settings
from backend.app.schemas.leads import LeadRecord
from backend.app.services.call_state import call_state_manager
from backend.app.services.csv_processor import save_evaluated_leads_csv

logger = logging.getLogger(__name__)

DEFAULT_PREWARM_GREETING = (
    "Hi there! Thanks for taking my call, I hope I'm catching you at a good time. "
    "How are you doing today?"
)

SYSTEM_NEGOTIATION_PERSONA = (
    "You are an articulate, charismatic, and strategic business development executive and negotiator for our Voice AI platform. "
    "Your goal is to guide the conversation smoothly, build trust, understand their requirements, and persuasively negotiate "
    "and convince them to invest in our business opportunities without sounding pushy, robotic, or overtly transactional. "
    "Maintain a warm, conversational, concise, professional, and natural tone suitable for telephone speech "
    "(strictly 1 to 2 short sentences per turn, maximum 25-30 words, no bullet points, no markdown formatting, no unpronounceable characters)."
)

def build_lead_persona(lead: LeadRecord) -> str:
    return (
        "You are an articulate, charismatic, and strategic business development executive and negotiator for our Voice AI platform.\n"
        f"You are currently speaking directly over the phone with {lead.name}.\n"
        f'The primary reason for this call is: "{lead.reason_for_calling}".\n\n'
        "Core Objectives:\n"
        "1. Frame our company's conversational AI and voice infrastructure as the ultimate high-ROI solution for their operational needs.\n"
        "2. Convince the customer to consider investing in our venture or partnering as an enterprise client.\n"
        "3. Be smooth, consultative, and persuasive—never pushy, aggressive, or overtly robotic.\n"
        "4. Spoken Dialogue Rules: Keep all responses to 1-2 short, punchy sentences (maximum 25-30 words). Never use lists, bullet points, asterisks, or markdown formatting."
    )

def build_lead_greeting(lead: LeadRecord) -> str:
    return (
        f"Hi {lead.name}! Thanks for taking my call. I'm reaching out regarding {lead.reason_for_calling}. "
        "I hope I caught you at a good time?"
    )

class TwilioProvider:
    def __init__(self):
        if settings.GEMINI_API_KEY:
            try:
                genai.configure(api_key=settings.GEMINI_API_KEY)
            except Exception as e:
                logger.warning(f"Error configuring Google GenAI: {e}")

    @property
    def client(self) -> Optional[Client]:
        """Dynamically instantiate Twilio Client so .env changes are respected."""
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        return None

    def trigger_call(self, to_number: str, lead_id: Optional[str] = None) -> str:
        """
        Initiate an outbound call via Twilio with status callbacks and lead identification.
        """
        client = self.client
        if not client:
            raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be configured in .env.")

        if not settings.TWILIO_FROM_NUMBER:
            raise ValueError("TWILIO_FROM_NUMBER must be configured in .env.")

        if not settings.SERVER_DOMAIN:
            raise ValueError("SERVER_DOMAIN is not set. A public domain (e.g. ngrok) is required for Twilio webhooks.")

        clean_domain = settings.SERVER_DOMAIN.replace("https://", "").replace("http://", "").strip("/")
        lead_param = f"?lead_id={lead_id}" if lead_id else ""
        twiml_url = f"https://{clean_domain}{settings.api_v1_str}/calls/twiml{lead_param}"
        status_callback_url = f"https://{clean_domain}{settings.api_v1_str}/calls/status-callback{lead_param}"

        call = client.calls.create(
            to=to_number,
            from_=settings.TWILIO_FROM_NUMBER,
            url=twiml_url,
            status_callback=status_callback_url,
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
            timeout=30  # Ring duration before timing out
        )
        return call.sid

    async def _generate_llm_response(self, chat_session, user_text: str) -> str:
        """Query Gemini Flash model via text prompting."""
        try:
            response = await chat_session.send_message_async(user_text)
            return response.text.strip() if response and response.text else ""
        except Exception as e:
            logger.error(f"Gemini LLM error: {e}")
            return "I hear you, and that makes sense. Could you share a bit more about what you're looking for?"

    async def _synthesize_and_stream_to_twilio(
        self,
        text: str,
        http_client: httpx.AsyncClient,
        twilio_ws: WebSocket,
        stream_sid: str
    ):
        """
        Sends text to Deepgram Aura TTS via HTTP REST requesting raw 8kHz headerless mu-law audio,
        then chunks it into 160-byte packets (20ms frames) and streams directly to Twilio WebSocket.
        """
        if not text.strip():
            return

        try:
            model = settings.DEEPGRAM_VOICE_MODEL or "aura-asteria-en"
            url = f"https://api.deepgram.com/v1/speak?model={model}&encoding=mulaw&sample_rate=8000&container=none"
            headers = {
                "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
                "Content-Type": "application/json"
            }
            body = {"text": text}

            response = await http_client.post(url, headers=headers, json=body)
            if response.status_code != 200:
                logger.error(f"Deepgram Aura TTS error: {response.status_code} - {response.text}")
                return

            raw_mulaw = response.content
            if not raw_mulaw:
                return

            # Transmit in 160-byte chunks (20ms frames at 8000Hz) to preserve standard telephony cadence
            chunk_size = 160
            for i in range(0, len(raw_mulaw), chunk_size):
                chunk = raw_mulaw[i : i + chunk_size]
                payload = base64.b64encode(chunk).decode("utf-8")
                await twilio_ws.send_json({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload}
                })
                await asyncio.sleep(0.018)  # ~18ms-20ms pacing

        except Exception as e:
            logger.warning(f"Deepgram Aura TTS / Twilio streaming warning: {e}")

    async def evaluate_lead_transcript(self, lead: LeadRecord, transcript: List[Dict[str, str]]):
        """
        Post-call evaluation: Analyzes dialogue transcript using Gemini to score
        investment probability and persistence to CSV.
        """
        if lead.investment_score is not None:
            return  # Already evaluated

        user_turns = [t for t in transcript if t.get("role") == "user"]
        if not user_turns:
            lead.investment_score = 0
            lead.interest_level = "Low"
            lead.evaluation_notes = "Call answered but disconnected without engagement"
            lead.status = "completed"
            await call_state_manager.update_lead(lead)
            return

        formatted_transcript = "\n".join([
            f"{t.get('role', 'speaker').title()}: {t.get('content', '')}"
            for t in transcript
        ])

        evaluation_prompt = f"""
Analyze the following phone conversation transcript between our AI sales agent and a prospect.
Prospect Name: {lead.name}
Reason for Calling: {lead.reason_for_calling}

Conversation Transcript:
{formatted_transcript}

Evaluate how likely this customer is to invest into our business or purchase our service.
Return ONLY a valid JSON object matching this schema:
{{
    "investment_score": <integer from 0 to 100>,
    "interest_level": "<High|Medium|Low>",
    "evaluation_notes": "<1-2 sentence concise explanation of their sentiment and objections>"
}}
"""
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            model_name = settings.GEMINI_MODEL or "gemini-2.0-flash"
            eval_model = genai.GenerativeModel(model_name=model_name)
            response = await eval_model.generate_content_async(evaluation_prompt)
            text = response.text.strip() if response and response.text else "{}"

            # Strip markdown formatting e.g. ```json ... ```
            if "```" in text:
                parts = text.split("```")
                if len(parts) >= 3:
                    inner = parts[1]
                    if inner.startswith("json"):
                        inner = inner[4:]
                    text = inner.strip()
                elif len(parts) == 2:
                    text = parts[1].strip()

            data = json.loads(text)
            lead.investment_score = int(data.get("investment_score", 50))
            lead.interest_level = str(data.get("interest_level", "Medium"))
            lead.evaluation_notes = str(data.get("evaluation_notes", "Evaluation completed."))
            lead.status = "completed"
        except Exception as e:
            logger.error(f"Post-call transcript evaluation error for {lead.name}: {e}")
            lead.investment_score = 0
            lead.interest_level = "Low"
            lead.evaluation_notes = f"Evaluation fallback due to parsing error: {e}"
            lead.status = "completed"

        await call_state_manager.update_lead(lead)

    async def handle_media_stream(self, twilio_ws: WebSocket, lead_id: Optional[str] = None):
        """
        Accepts Twilio WebSocket and runs the outbound conversational voice pipeline:
        1. Pre-warms the call by speaking the first personalized greeting within milliseconds of pickup.
        2. Configures Gemini with a personalized sales negotiation persona.
        3. STT: Streams Twilio 8kHz mu-law audio to Deepgram Live WebSocket (nova-2).
        4. LLM: Triggers Gemini upon speech_final / is_final detection.
        5. TTS: Synthesizes response using Deepgram Aura (8kHz mu-law) and streams directly to Twilio.
        6. Post-Call: Scores customer investment probability upon completion and persists to CSV.
        """
        await twilio_ws.accept()

        if not settings.DEEPGRAM_API_KEY:
            logger.error("DEEPGRAM_API_KEY is not configured in .env.")
            await twilio_ws.close(code=1008, reason="DEEPGRAM_API_KEY is not configured.")
            return

        if not settings.GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY is not configured in .env.")
            await twilio_ws.close(code=1008, reason="GEMINI_API_KEY is not configured.")
            return

        dg_client = AsyncDeepgramClient(api_key=settings.DEEPGRAM_API_KEY)
        stream_sid: Optional[str] = None
        call_sid: Optional[str] = None
        current_lead: Optional[LeadRecord] = None
        stream_ready = asyncio.Event()
        processing_lock = asyncio.Lock()
        greeting_sent = False
        chat_session = None

        # Reusable async HTTP client for Deepgram Aura TTS requests
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            try:
                # Connect to Deepgram Live WebSocket configured for 8kHz mu-law
                async with dg_client.listen.v1.connect(
                    model="nova-2",
                    encoding="mulaw",
                    sample_rate=8000,
                    channels=1,
                    endpointing=300,
                    smart_format=True
                ) as dg_socket:

                    async def on_deepgram_message(message):
                        nonlocal stream_sid, chat_session, current_lead
                        try:
                            if not isinstance(message, ListenV1Results):
                                return

                            is_final = getattr(message, "is_final", False)
                            speech_final = getattr(message, "speech_final", False)

                            if not (is_final or speech_final):
                                return

                            channel = getattr(message, "channel", None)
                            if not channel or not channel.alternatives:
                                return

                            transcript = channel.alternatives[0].transcript.strip()
                            if not transcript:
                                return

                            logger.info(f"User Transcribed: {transcript} (speech_final={speech_final}, is_final={is_final})")

                            # Record user speech in session manager
                            active_key = stream_sid or lead_id
                            if active_key:
                                await call_state_manager.append_transcript(active_key, "user", transcript)

                            async def run_pipeline():
                                async with processing_lock:
                                    if not stream_sid or not chat_session:
                                        return
                                    # 1. Query Gemini text LLM
                                    reply_text = await self._generate_llm_response(chat_session, transcript)
                                    logger.info(f"AI Response: {reply_text}")

                                    # Record AI reply in session manager
                                    if active_key:
                                        await call_state_manager.append_transcript(active_key, "assistant", reply_text)

                                    # 2. Synthesize with Deepgram Aura and stream to Twilio
                                    await self._synthesize_and_stream_to_twilio(
                                        reply_text,
                                        http_client,
                                        twilio_ws,
                                        stream_sid
                                    )

                            asyncio.create_task(run_pipeline())

                        except Exception as e:
                            logger.warning(f"Warning processing Deepgram message: {e}")

                    dg_socket.on(EventType.MESSAGE, on_deepgram_message)
                    dg_listener_task = asyncio.create_task(dg_socket.start_listening())

                    async def play_prewarm_greeting():
                        nonlocal greeting_sent, chat_session, current_lead
                        try:
                            await stream_ready.wait()
                            async with processing_lock:
                                if not greeting_sent and stream_sid:
                                    greeting_sent = True

                                    # Resolve active lead
                                    if not current_lead and lead_id:
                                        current_lead = await call_state_manager.get_lead_by_id(lead_id)
                                    if not current_lead and stream_sid:
                                        current_lead = await call_state_manager.get_lead_by_stream_sid(stream_sid)

                                    if current_lead:
                                        greeting_text = build_lead_greeting(current_lead)
                                        persona = build_lead_persona(current_lead)
                                    else:
                                        greeting_text = DEFAULT_PREWARM_GREETING
                                        persona = SYSTEM_NEGOTIATION_PERSONA

                                    # Initialize Gemini model with specific persona
                                    genai.configure(api_key=settings.GEMINI_API_KEY)
                                    model_name = settings.GEMINI_MODEL or "gemini-2.0-flash"
                                    model = genai.GenerativeModel(
                                        model_name=model_name,
                                        system_instruction=persona
                                    )

                                    # Prime conversation history with initial opening greeting
                                    initial_history = [
                                        {"role": "user", "parts": ["[The customer answers the phone call]"]},
                                        {"role": "model", "parts": [greeting_text]}
                                    ]
                                    chat_session = model.start_chat(history=initial_history)

                                    # Record assistant greeting in transcript
                                    active_key = stream_sid or lead_id
                                    if active_key:
                                        await call_state_manager.append_transcript(active_key, "assistant", greeting_text)

                                    logger.info(f"Pre-warming call with first-speaker greeting: {greeting_text}")
                                    await self._synthesize_and_stream_to_twilio(
                                        greeting_text,
                                        http_client,
                                        twilio_ws,
                                        stream_sid
                                    )
                        except Exception as e:
                            logger.warning(f"Initial pre-warm greeting warning: {e}")

                    # Spawn greeting as an unmonitored background task
                    asyncio.create_task(play_prewarm_greeting())

                    # Task to read audio packets from Twilio and pipe into Deepgram
                    async def twilio_to_deepgram():
                        nonlocal stream_sid, call_sid, current_lead
                        try:
                            while True:
                                msg = await twilio_ws.receive_json()
                                event = msg.get("event")

                                if event == "start":
                                    stream_sid = msg["start"]["streamSid"]
                                    call_sid = msg["start"].get("callSid")

                                    # Bind identifiers in call_state_manager
                                    effective_lead_id = lead_id
                                    if not effective_lead_id and call_sid:
                                        bound_lead = await call_state_manager.get_lead_by_call_sid(call_sid)
                                        if bound_lead:
                                            effective_lead_id = bound_lead.id

                                    if effective_lead_id:
                                        await call_state_manager.bind_stream_to_lead(effective_lead_id, stream_sid)
                                        if call_sid:
                                            await call_state_manager.bind_call_sid(effective_lead_id, call_sid)
                                        current_lead = await call_state_manager.get_lead_by_id(effective_lead_id)

                                    stream_ready.set()
                                    logger.info(f"Twilio stream started with streamSid: {stream_sid}, callSid: {call_sid}")

                                elif event == "media":
                                    payload = msg["media"]["payload"]
                                    audio_mulaw = base64.b64decode(payload)
                                    await dg_socket.send_media(audio_mulaw)

                                elif event == "stop":
                                    logger.info(f"Twilio stream stopped: {stream_sid}")
                                    break

                        except WebSocketDisconnect:
                            logger.info("Twilio WebSocket disconnected.")
                        except Exception as e:
                            logger.warning(f"Twilio WebSocket read warning: {e}")

                    twilio_task = asyncio.create_task(twilio_to_deepgram())

                    # Wait for either Twilio or Deepgram connection to close
                    done, pending = await asyncio.wait(
                        [twilio_task, dg_listener_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )

                    for task in pending:
                        task.cancel()

            except Exception as e:
                logger.error(f"Error during audio stream session: {e}")
                try:
                    await twilio_ws.close()
                except Exception:
                    pass
            finally:
                # Perform post-call evaluation if lead exists and was engaged
                try:
                    active_key = stream_sid or lead_id or call_sid
                    if active_key:
                        if not current_lead and lead_id:
                            current_lead = await call_state_manager.get_lead_by_id(lead_id)
                        if not current_lead and stream_sid:
                            current_lead = await call_state_manager.get_lead_by_stream_sid(stream_sid)

                        if current_lead and current_lead.investment_score is None:
                            transcript = await call_state_manager.get_transcript(active_key)
                            await self.evaluate_lead_transcript(current_lead, transcript)
                            leads = await call_state_manager.get_leads_by_batch(current_lead.batch_id)
                            if leads:
                                save_evaluated_leads_csv(current_lead.batch_id, leads)
                except Exception as e:
                    logger.error(f"Error in post-call evaluation hook: {e}")

telephony_provider = TwilioProvider()
