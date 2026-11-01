import csv
import os
import re
import sys
import uuid
from pathlib import Path
from typing import TextIO, List, Optional
from fastapi import HTTPException
from backend.app.schemas.leads import CsvProcessingResponse, AcceptedLead, RejectedRow, LeadRecord
from backend.app.core.config import settings

REQUIRED_HEADERS = {"name", "phone"}

# Pre-compiled regular expressions for maximum row-processing throughput
RE_PHONE_STRIP = re.compile(r'[\s\-\(\)\.]')
RE_E164 = re.compile(r'^\+[1-9]\d{7,14}$')

# Increase CSV field size limit to handle large freeform values safely
try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2147483647)

def normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_")

def normalize_phone(phone: str) -> str:
    phone = RE_PHONE_STRIP.sub('', phone)
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    return phone

def is_valid_phone(phone: str) -> bool:
    # E.164: + followed by 8-15 digits, first digit non-zero
    return bool(RE_E164.match(phone))

def parse_leads_csv(file_obj: TextIO, batch_id: Optional[str] = None) -> List[LeadRecord]:
    """
    Parses and strictly validates a 3-column leads CSV for outbound calling:
    Required columns: 'name', 'number' (or 'phone'), 'reason for calling' (or 'reason_for_calling').
    Rejects with HTTP 422 if any required header is missing, or if any row
    lacks one of these 3 fields or has an invalid E.164 phone number.
    """
    try:
        reader = csv.reader(file_obj)
        try:
            raw_headers = next(reader)
        except StopIteration:
            raise HTTPException(status_code=422, detail="File is empty.")

        if not raw_headers or all(not h.strip() for h in raw_headers):
            raise HTTPException(status_code=422, detail="No headers found in CSV file.")

        normalized_headers = [normalize_header(h) for h in raw_headers]

        name_idx = None
        number_idx = None
        reason_idx = None

        for idx, h in enumerate(normalized_headers):
            if h in ("name", "full_name", "first_name"):
                name_idx = idx
            elif h in ("number", "phone", "phone_number", "mobile"):
                number_idx = idx
            elif h in ("reason_for_calling", "reason", "reason_for_call", "campaign_objective"):
                reason_idx = idx

        missing_fields = []
        if name_idx is None:
            missing_fields.append("name")
        if number_idx is None:
            missing_fields.append("number")
        if reason_idx is None:
            missing_fields.append("reason for calling")

        if missing_fields:
            raise HTTPException(
                status_code=422,
                detail=f"CSV missing required column(s): {', '.join(missing_fields)}. Required: 'name', 'number', 'reason for calling'."
            )

        header_count = len(normalized_headers)
        leads: List[LeadRecord] = []
        effective_batch_id = batch_id or str(uuid.uuid4())
        row_number = 1  # Header was row 1

        for row in reader:
            row_number += 1
            if not row or all(not cell.strip() for cell in row):
                continue

            if len(row) != header_count:
                raise HTTPException(
                    status_code=422,
                    detail=f"Row {row_number}: Expected {header_count} columns, but got {len(row)}."
                )

            name = row[name_idx].strip()
            if not name:
                raise HTTPException(
                    status_code=422,
                    detail=f"Row {row_number}: Missing required field 'name'."
                )

            raw_number = row[number_idx].strip()
            if not raw_number:
                raise HTTPException(
                    status_code=422,
                    detail=f"Row {row_number}: Missing required field 'number'."
                )

            number = normalize_phone(raw_number)
            if not is_valid_phone(number):
                raise HTTPException(
                    status_code=422,
                    detail=f"Row {row_number}: Phone number '{raw_number}' is invalid. Must be in E.164 format."
                )

            reason = row[reason_idx].strip()
            if not reason:
                raise HTTPException(
                    status_code=422,
                    detail=f"Row {row_number}: Missing required field 'reason for calling'."
                )

            leads.append(
                LeadRecord(
                    id=str(uuid.uuid4()),
                    batch_id=effective_batch_id,
                    name=name,
                    number=number,
                    reason_for_calling=reason,
                    status="pending",
                    retry_count=0
                )
            )

        if not leads:
            raise HTTPException(status_code=422, detail="CSV file contains no valid data rows.")

        return leads

    except HTTPException:
        raise
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="File must be UTF-8 encoded.")
    except csv.Error as e:
        raise HTTPException(status_code=422, detail=f"Malformed CSV: {str(e)}")

def save_evaluated_leads_csv(batch_id: str, leads: List[LeadRecord]) -> Path:
    """
    Persists evaluated leads to a CSV in PROCESSED_CSV_DIR.
    Ensures atomic write via temporary file replacement.
    Preserves original columns ('name', 'number', 'reason for calling') and
    appends 'Status', 'Retry_Count', 'Investment_Probability_Score', and 'Evaluation_Notes'.
    """
    output_dir = Path(settings.PROCESSED_CSV_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    target_path = output_dir / f"leads_evaluated_{batch_id}.csv"
    tmp_path = output_dir / f".leads_evaluated_{batch_id}_{uuid.uuid4().hex}.tmp"

    fieldnames = [
        "name",
        "number",
        "reason for calling",
        "Status",
        "Retry_Count",
        "Investment_Probability_Score",
        "Evaluation_Notes"
    ]

    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for lead in leads:
            score_str = str(lead.investment_score) if lead.investment_score is not None else ""
            writer.writerow({
                "name": lead.name,
                "number": lead.number,
                "reason for calling": lead.reason_for_calling,
                "Status": lead.status,
                "Retry_Count": lead.retry_count,
                "Investment_Probability_Score": score_str,
                "Evaluation_Notes": lead.evaluation_notes or ""
            })

    # Atomic replace
    tmp_path.replace(target_path)
    return target_path

def process_csv(file_obj: TextIO, agent_id: str) -> CsvProcessingResponse:
    """
    Legacy CSV processor used for agent assignment lead validation.
    Maintained for complete backward compatibility.
    """
    try:
        reader = csv.reader(file_obj)
        try:
            raw_headers = next(reader)
        except StopIteration:
            raise HTTPException(status_code=400, detail="File is empty.")

        # Handle completely blank header row or empty list
        if not raw_headers or all(not h.strip() for h in raw_headers):
            raise HTTPException(status_code=400, detail="No headers found.")

        # Normalize headers
        normalized_headers = [normalize_header(h) for h in raw_headers]

        # Check for duplicates
        if len(normalized_headers) != len(set(normalized_headers)):
            raise HTTPException(status_code=400, detail="Duplicate headers found after normalization.")

        # Check for required headers
        missing_headers = REQUIRED_HEADERS - set(normalized_headers)
        if missing_headers:
            raise HTTPException(status_code=400, detail=f"Missing required headers: {', '.join(missing_headers)}")

        header_count = len(normalized_headers)
        name_idx = normalized_headers.index("name")
        phone_idx = normalized_headers.index("phone")

        extra_field_indices = [
            i for i, h in enumerate(normalized_headers) if h not in REQUIRED_HEADERS
        ]

        accepted_leads: List[AcceptedLead] = []
        rejected_rows: List[RejectedRow] = []

        row_number = 1  # Header is row 1

        for row in reader:
            row_number += 1

            # Ignore completely blank rows
            if not row or all(not cell.strip() for cell in row):
                continue

            errors = []

            if len(row) != header_count:
                errors.append(f"Expected {header_count} columns, but got {len(row)}.")
                rejected_rows.append(RejectedRow(row_number=row_number, errors=errors))
                continue

            name = row[name_idx].strip()
            if not name:
                errors.append("Name cannot be empty.")

            raw_phone = row[phone_idx].strip()
            phone = normalize_phone(raw_phone)
            if not is_valid_phone(phone):
                errors.append("Phone number is invalid. Must be in E.164 format.")

            if errors:
                rejected_rows.append(RejectedRow(row_number=row_number, errors=errors))
            else:
                extra_fields = {
                    normalized_headers[i]: row[i].strip() for i in extra_field_indices
                }
                accepted_leads.append(
                    AcceptedLead(
                        row_number=row_number,
                        name=name,
                        phone=phone,
                        extra_fields=extra_fields,
                        assigned_agent_id=agent_id
                    )
                )

        if len(accepted_leads) + len(rejected_rows) == 0:
            raise HTTPException(status_code=400, detail="File contains no data rows.")

        return CsvProcessingResponse(
            status="processed",
            agent_id=agent_id,
            total_rows=len(accepted_leads) + len(rejected_rows),
            accepted_count=len(accepted_leads),
            rejected_count=len(rejected_rows),
            accepted_leads=accepted_leads,
            rejected_rows=rejected_rows
        )

    except HTTPException:
        raise
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded.")
    except csv.Error as e:
        raise HTTPException(status_code=400, detail=f"Malformed CSV: {str(e)}")
