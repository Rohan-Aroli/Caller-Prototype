from pydantic import BaseModel, Field
from typing import List, Dict, Any

class AcceptedLead(BaseModel):
    row_number: int
    name: str
    phone: str
    extra_fields: Dict[str, Any] = Field(default_factory=dict)
    assigned_agent_id: str

class RejectedRow(BaseModel):
    row_number: int
    errors: List[str]

class CsvProcessingResponse(BaseModel):
    status: str = "processed"
    agent_id: str
    total_rows: int
    accepted_count: int
    rejected_count: int
    accepted_leads: List[AcceptedLead] = Field(default_factory=list)
    rejected_rows: List[RejectedRow] = Field(default_factory=list)
