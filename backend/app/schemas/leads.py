import uuid
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class AcceptedLead(BaseModel):
    row_number: int
    name: str
    phone: str
    extra_fields: Dict[str, Any] = Field(default_factory=dict)
    assigned_agent_id: str

class RejectedRow(BaseModel):
    row_number: int
    errors: List[str]

class LeadRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    number: str
    reason_for_calling: str
    status: str = "pending"
    retry_count: int = 0
    investment_score: Optional[int] = None
    interest_level: Optional[str] = None
    evaluation_notes: Optional[str] = None

class CsvProcessingResponse(BaseModel):
    status: str = "processed"
    agent_id: str
    total_rows: int
    accepted_count: int
    rejected_count: int
    accepted_leads: List[AcceptedLead] = Field(default_factory=list)
    rejected_rows: List[RejectedRow] = Field(default_factory=list)
    batch_id: Optional[str] = None
    download_url: Optional[str] = None
    leads: Optional[List[LeadRecord]] = None
