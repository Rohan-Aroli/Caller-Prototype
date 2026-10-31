import json
import base64
import asyncio
import audioop
import logging
from typing import Optional
from twilio.rest import Client
import websockets
from fastapi import WebSocket, WebSocketDisconnect

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

class TwilioProvider:
    def __init__(self):
        # We only initialize Twilio Client if credentials are provided
        if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
            self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        else:
            self.client = None
            logger.warning("Twilio credentials not found. Calls cannot be triggered.")

        # The Gemini Multimodal Live API websocket endpoint
        self.gemini_url = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"

        # Audio configuration
        self.twilio_sample_rate = 8000
        self.gemini_sample_rate = 16000
        self.twilio_sample_width = 1 # 8-bit mu-law
        self.gemini_sample_width = 2 # 16-bit PCM

    def trigger_call(self, to_number: str) -> str:
        if not self.client:
            raise ValueError("Twilio client is not initialized.")

        if not settings.SERVER_DOMAIN:
            raise ValueError("SERVER_DOMAIN is not set. Twilio needs a public endpoint.")

        twiml_url = f"https://{settings.SERVER_DOMAIN}{settings.api_v1_str}/calls/twiml"

        call = self.client.calls.create(
            to=to_number,
            from_=settings.TWILIO_FROM_NUMBER,
            url=twiml_url
        )
        return call.sid

    async def handle_media_stream(self, twilio_ws: WebSocket):
        """
        Accepts the Twilio websocket, opens a websocket to Gemini,
        and bridges the audio bidirectionally.
        """
        await twilio_ws.accept()

        if not settings.GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY is not set.")
            await twilio_ws.close()
            return

        gemini_ws_url = f"{self.gemini_url}?key={settings.GEMINI_API_KEY}"

        try:
            async with websockets.connect(gemini_ws_url) as gemini_ws:
                # Send the initial setup message to Gemini
                setup_msg = {
                    "setup": {
                        "model": "models/gemini-2.0-flash-exp",
                        "generationConfig": {
                            "responseModalities": ["AUDIO"]
                        }
                    }
                }
                await gemini_ws.send(json.dumps(setup_msg))

                # Wait for the setup response
                setup_response_raw = await gemini_ws.recv()

                stream_sid = None

                # Task for receiving from Twilio and sending to Gemini
                async def twilio_to_gemini():
                    nonlocal stream_sid
                    try:
                        while True:
                            msg = await twilio_ws.receive_json()
                            event = msg.get("event")

                            if event == "start":
                                stream_sid = msg["start"]["streamSid"]
                                logger.info(f"Started Twilio stream: {stream_sid}")
                            elif event == "media":
                                payload = msg["media"]["payload"]
                                audio_mulaw = base64.b64decode(payload)

                                # Convert mu-law -> linear PCM (8kHz -> 8kHz, 16-bit)
                                audio_lin_8k = audioop.ulaw2lin(audio_mulaw, self.gemini_sample_width)
                                # Resample linear PCM (8kHz -> 16kHz)
                                audio_lin_16k, _ = audioop.ratecv(
                                    audio_lin_8k, self.gemini_sample_width, 1,
                                    self.twilio_sample_rate, self.gemini_sample_rate, None
                                )

                                # Send to Gemini
                                gemini_audio_msg = {
                                    "realtimeInput": {
                                        "mediaChunks": [
                                            {
                                                "mimeType": "audio/pcm;rate=16000",
                                                "data": base64.b64encode(audio_lin_16k).decode('utf-8')
                                            }
                                        ]
                                    }
                                }
                                await gemini_ws.send(json.dumps(gemini_audio_msg))

                            elif event == "stop":
                                logger.info(f"Twilio stream stopped: {stream_sid}")
                                break
                    except WebSocketDisconnect:
                        logger.info("Twilio websocket disconnected.")
                    except Exception as e:
                        logger.error(f"Error in twilio_to_gemini: {e}")

                # Task for receiving from Gemini and sending to Twilio
                async def gemini_to_twilio():
                    try:
                        while True:
                            if not stream_sid:
                                await asyncio.sleep(0.01)
                                continue

                            msg_str = await gemini_ws.recv()
                            msg = json.loads(msg_str)

                            if "serverContent" in msg:
                                server_content = msg["serverContent"]
                                if "modelTurn" in server_content:
                                    parts = server_content["modelTurn"].get("parts", [])
                                    for part in parts:
                                        if "inlineData" in part:
                                            # Audio from Gemini (PCM 16kHz)
                                            audio_data_b64 = part["inlineData"].get("data")
                                            if audio_data_b64:
                                                audio_pcm_16k = base64.b64decode(audio_data_b64)

                                                # Resample PCM (16kHz -> 8kHz)
                                                audio_pcm_8k, _ = audioop.ratecv(
                                                    audio_pcm_16k, self.gemini_sample_width, 1,
                                                    self.gemini_sample_rate, self.twilio_sample_rate, None
                                                )
                                                # Convert linear PCM -> mu-law
                                                audio_mulaw = audioop.lin2ulaw(audio_pcm_8k, self.gemini_sample_width)

                                                twilio_media_msg = {
                                                    "event": "media",
                                                    "streamSid": stream_sid,
                                                    "media": {
                                                        "payload": base64.b64encode(audio_mulaw).decode('utf-8')
                                                    }
                                                }
                                                await twilio_ws.send_json(twilio_media_msg)

                    except websockets.exceptions.ConnectionClosed:
                        logger.info("Gemini websocket closed.")
                    except Exception as e:
                        logger.error(f"Error in gemini_to_twilio: {e}")

                # Run both tasks concurrently
                await asyncio.gather(
                    twilio_to_gemini(),
                    gemini_to_twilio()
                )

        except Exception as e:
            logger.error(f"Error connecting to Gemini WebSocket: {e}")
            try:
                await twilio_ws.close()
            except Exception:
                pass

telephony_provider = TwilioProvider()
