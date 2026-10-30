export interface RejectedRow {
  row_number: number;
  errors: string[];
}

export interface AcceptedLead {
  name: string;
  phone: string;
  email?: string;
  address?: string;
  [key: string]: any;
}

export interface CsvProcessingResponse {
  status: string;
  agent_id: string;
  total_rows: number;
  accepted_count: number;
  rejected_count: number;
  accepted_leads: AcceptedLead[];
  rejected_rows: RejectedRow[];
}
