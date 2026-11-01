import asyncio
import logging
from typing import Dict, List, Optional
from backend.app.schemas.leads import LeadRecord

logger = logging.getLogger(__name__)

class LeadSessionManager:
    """
    Thread-safe in-memory session manager to track active and pending leads,
    map active call_sid and stream_sid to the corresponding LeadRecord,
    and persist conversation transcripts during active calls.
    """
    def __init__(self):
        self._lock = asyncio.Lock()
        self._leads: Dict[str, LeadRecord] = {}  # lead_id -> LeadRecord
        self._call_to_lead: Dict[str, str] = {}  # call_sid -> lead_id
        self._stream_to_lead: Dict[str, str] = {}  # stream_sid -> lead_id
        self._transcripts: Dict[str, List[Dict[str, str]]] = {}  # lead_id -> list of {"role": str, "content": str}
        self._batches: Dict[str, List[str]] = {}  # batch_id -> list of lead_ids

    async def register_lead(self, lead: LeadRecord):
        """Register a new lead into the manager."""
        async with self._lock:
            self._leads[lead.id] = lead
            if lead.batch_id not in self._batches:
                self._batches[lead.batch_id] = []
            if lead.id not in self._batches[lead.batch_id]:
                self._batches[lead.batch_id].append(lead.id)
            if lead.id not in self._transcripts:
                self._transcripts[lead.id] = []
            logger.debug(f"Registered lead: {lead.id} ({lead.name}) for batch {lead.batch_id}")

    async def bind_call_sid(self, lead_id: str, call_sid: str):
        """Map active Twilio CallSid to a LeadRecord ID."""
        async with self._lock:
            self._call_to_lead[call_sid] = lead_id
            logger.debug(f"Bound CallSid {call_sid} to lead {lead_id}")

    async def bind_stream_sid(self, call_sid: str, stream_sid: str):
        """Map active Twilio StreamSid to CallSid's associated LeadRecord."""
        async with self._lock:
            lead_id = self._call_to_lead.get(call_sid)
            if lead_id:
                self._stream_to_lead[stream_sid] = lead_id
                logger.debug(f"Bound StreamSid {stream_sid} to lead {lead_id} via CallSid {call_sid}")
            else:
                logger.warning(f"No lead found for CallSid {call_sid} when binding StreamSid {stream_sid}")

    async def bind_stream_to_lead(self, lead_id: str, stream_sid: str):
        """Directly map active Twilio StreamSid to a LeadRecord ID."""
        async with self._lock:
            self._stream_to_lead[stream_sid] = lead_id
            logger.debug(f"Directly bound StreamSid {stream_sid} to lead {lead_id}")

    async def append_transcript(self, session_key: str, role: str, text: str):
        """
        Append a message turn to the session transcript.
        session_key can be a call_sid, stream_sid, or lead_id.
        """
        async with self._lock:
            lead_id = session_key
            if lead_id in self._stream_to_lead:
                lead_id = self._stream_to_lead[lead_id]
            elif lead_id in self._call_to_lead:
                lead_id = self._call_to_lead[lead_id]

            if lead_id not in self._transcripts:
                self._transcripts[lead_id] = []

            self._transcripts[lead_id].append({"role": role, "content": text})

    async def get_lead_by_call_sid(self, call_sid: str) -> Optional[LeadRecord]:
        """Look up active LeadRecord by Twilio CallSid."""
        async with self._lock:
            lead_id = self._call_to_lead.get(call_sid)
            return self._leads.get(lead_id) if lead_id else None

    async def get_lead_by_stream_sid(self, stream_sid: str) -> Optional[LeadRecord]:
        """Look up active LeadRecord by Twilio StreamSid."""
        async with self._lock:
            lead_id = self._stream_to_lead.get(stream_sid)
            return self._leads.get(lead_id) if lead_id else None

    async def get_lead_by_id(self, lead_id: str) -> Optional[LeadRecord]:
        """Look up LeadRecord by lead ID."""
        async with self._lock:
            return self._leads.get(lead_id)

    async def get_transcript(self, session_key: str) -> List[Dict[str, str]]:
        """
        Retrieve all recorded dialogue turns for the given session_key
        (call_sid, stream_sid, or lead_id).
        """
        async with self._lock:
            lead_id = session_key
            if lead_id in self._stream_to_lead:
                lead_id = self._stream_to_lead[lead_id]
            elif lead_id in self._call_to_lead:
                lead_id = self._call_to_lead[lead_id]

            return list(self._transcripts.get(lead_id, []))

    async def get_leads_by_batch(self, batch_id: str) -> List[LeadRecord]:
        """Retrieve all LeadRecords belonging to a batch."""
        async with self._lock:
            lead_ids = self._batches.get(batch_id, [])
            return [self._leads[lid] for lid in lead_ids if lid in self._leads]

    async def update_lead(self, lead: LeadRecord):
        """Update an existing LeadRecord in memory."""
        async with self._lock:
            self._leads[lead.id] = lead

call_state_manager = LeadSessionManager()
