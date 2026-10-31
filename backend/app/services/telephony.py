import json
import base64
import asyncio
import logging
from typing import Optional
from twilio.rest import Client
from fastapi import WebSocket, WebSocketDisconnect
import httpx
import google.generativeai as genai
from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v1.types.listen_v1results import ListenV1Results

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

class TwilioProvider:
    def __init__(self):
        # Initialize Google Generative AI client once if API key is present
        if settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)

    @property
    def client(self) -> Optional[Client]:
        """Dynamically instantiate or reuse Twilio Client so .env changes are respected."""
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        return None

    def trigger_call(self, to_number: str) -> str:
        client = self.client
        if not client:
            raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be configured in .env.")

        if not settings.TWILIO_FROM_NUMBER:
            raise ValueError("TWILIO_FROM_NUMBER must be configured in .env.")

        if not settings.SERVER_DOMAIN:
            raise ValueError("SERVER_DOMAIN is not set. A public domain (e.g. ngrok) is required for Twilio webhooks.")

        # Strip any accidental http:// or https:// from domain
        clean_domain = settings.SERVER_DOMAIN.replace("https://", "").replace("http://", "").strip("/")
        twiml_url = f"https://{clean_domain}{settings.api_v1_str}/calls/twiml"

        call = client.calls.create(
            to=to_number,
            from_=settings.TWILIO_FROM_NUMBER,
            url=twiml_url
        )
        return call.sid

    async def _generate_llm_response(self, chat_session, user_text: str) -> str:
        """Query standard Gemini Flash model via text prompting."""
        try:
            response = await chat_session.send_message_async(user_text)
            return response.text.strip() if response and response.text else ""
        except Exception as e:
            logger.error(f"Gemini LLM error: {e}")
            return "I apologize, I had trouble processing that. Could you please repeat?"

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

    async def handle_media_stream(self, twilio_ws: WebSocket):
        """
        Accepts Twilio WebSocket and runs a consolidated, 100% free pipeline:
        1. STT: Streams Twilio 8kHz mu-law audio to Deepgram Live WebSocket (nova-2).
        2. LLM: Triggers Gemini Flash REST upon speech_final / is_final detection.
        3. TTS: Synthesizes response using Deepgram Aura TTS (aura-asteria-en) returning 8kHz mu-law.
        4. Playback: Streams 160-byte packets directly to Twilio without intermediate conversions.
        """
        await twilio_ws.accept()

        # Validate necessary API keys
        if not settings.DEEPGRAM_API_KEY:
            logger.error("DEEPGRAM_API_KEY is not configured in .env.")
            await twilio_ws.close(code=1008, reason="DEEPGRAM_API_KEY is not configured.")
            return

        if not settings.GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY is not configured in .env.")
            await twilio_ws.close(code=1008, reason="GEMINI_API_KEY is not configured.")
            return

        # Initialize Clients
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name="gemini-3.5-flash-lite",
            system_instruction=(
                "You are an AI phone assistant for an inbound/outbound call. "
                "Keep responses concise, natural, conversational, and direct (1-2 sentences), "
                "suitable for spoken conversation over a phone call."
            )
        )
        chat_session = model.start_chat(history=[])

        dg_client = AsyncDeepgramClient(api_key=settings.DEEPGRAM_API_KEY)
        stream_sid: Optional[str] = None
        stream_ready = asyncio.Event()
        processing_lock = asyncio.Lock()

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

                    # Callback for Deepgram transcription results
                    async def on_deepgram_message(message):
                        nonlocal stream_sid
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

                            # Trigger LLM -> Deepgram Aura TTS pipeline under lock to prevent race conditions
                            async def run_pipeline():
                                async with processing_lock:
                                    if not stream_sid:
                                        return
                                    # 1. Query Gemini text LLM
                                    reply_text = await self._generate_llm_response(chat_session, transcript)
                                    logger.info(f"AI Response: {reply_text}")

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

                    # Start Deepgram listener task
                    dg_listener_task = asyncio.create_task(dg_socket.start_listening())

                    # Task to read audio from Twilio and pipe into Deepgram
                    async def twilio_to_deepgram():
                        nonlocal stream_sid
                        try:
                            while True:
                                msg = await twilio_ws.receive_json()
                                event = msg.get("event")

                                if event == "start":
                                    stream_sid = msg["start"]["streamSid"]
                                    stream_ready.set()
                                    logger.info(f"Twilio stream started with streamSid: {stream_sid}")
                                elif event == "media":
                                    payload = msg["media"]["payload"]
                                    audio_mulaw = base64.b64decode(payload)
                                    # Send raw 8kHz mu-law audio directly to Deepgram STT
                                    await dg_socket.send_media(audio_mulaw)
                                elif event == "stop":
                                    logger.info(f"Twilio stream stopped: {stream_sid}")
                                    break

                        except WebSocketDisconnect:
                            logger.info("Twilio WebSocket disconnected.")
                        except Exception as e:
                            logger.warning(f"Twilio WebSocket read warning: {e}")

                    twilio_task = asyncio.create_task(twilio_to_deepgram())

                    # Wait until Twilio or Deepgram completes
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

telephony_provider = TwilioProvider()
