import csv
import re
import sys
from typing import TextIO, List
from fastapi import HTTPException
from backend.app.schemas.leads import CsvProcessingResponse, AcceptedLead, RejectedRow

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

def process_csv(file_obj: TextIO, agent_id: str) -> CsvProcessingResponse:
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

    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded.")
    except csv.Error as e:
        raise HTTPException(status_code=400, detail=f"Malformed CSV: {str(e)}")
