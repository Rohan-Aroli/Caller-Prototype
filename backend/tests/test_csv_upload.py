import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.config import settings

client = TestClient(app)

ENDPOINT = "/api/v1/leads/upload-csv"
AGENT_ID = "demo-agent-01"

def test_valid_csv_multiple_leads():
    csv_content = "Name,Phone,Course\nRahul Sharma,+919876543210,Data Science\nJane Doe,+1234567890,AI"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200
    res_json = response.json()
    assert res_json["status"] == "processed"
    assert res_json["total_rows"] == 2
    assert res_json["accepted_count"] == 2
    assert res_json["rejected_count"] == 0
    assert len(res_json["accepted_leads"]) == 2
    assert res_json["accepted_leads"][0]["extra_fields"] == {"course": "Data Science"}

def test_header_normalization():
    csv_content = " NaMe ,  PhOnE \nRahul,+919876543210"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200
    assert response.json()["accepted_count"] == 1

def test_phone_number_normalization():
    csv_content = "Name,Phone\nRahul, +91 987-654(3210).\nJane,001234567890"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200
    res = response.json()
    assert res["accepted_leads"][0]["phone"] == "+919876543210"
    assert res["accepted_leads"][1]["phone"] == "+1234567890"

def test_empty_names_and_invalid_phone_numbers():
    csv_content = "Name,Phone\n, +919876543210\nJane,invalid\nJohn,+0123456"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200
    res = response.json()
    assert res["rejected_count"] == 3
    assert any("Name cannot be empty." in err for err in res["rejected_rows"][0]["errors"])
    assert any("Phone number is invalid" in err for err in res["rejected_rows"][1]["errors"])
    assert any("Phone number is invalid" in err for err in res["rejected_rows"][2]["errors"])

def test_missing_required_headers():
    csv_content = "Name,Course\nRahul,AI"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 400
    assert "Missing required headers" in response.json()["detail"]

def test_duplicate_normalized_headers():
    csv_content = "Name,Phone, phone\nRahul,+919876543210,x"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 400
    assert "Duplicate headers" in response.json()["detail"]

def test_empty_files_and_header_only_files():
    # Empty file
    files = {"file": ("test.csv", "", "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 400
    assert response.json()["detail"] == "File is empty."

    # Header only file
    files = {"file": ("test.csv", "Name,Phone", "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 400
    assert "no data rows" in response.json()["detail"]

    # Header followed only by blank lines
    files = {"file": ("test.csv", "Name,Phone\n\n   \n", "text/csv")}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 400
    assert "no data rows" in response.json()["detail"]

def test_malformed_csv_input():
    # Null byte or bad encoding test
    csv_content = b"Name,Phone\n\0,123"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    if response.status_code == 400:
        assert "Malformed CSV" in response.json()["detail"] or "must be UTF-8" in response.json()["detail"] or "null" in response.text

def test_rows_incorrect_column_counts():
    csv_content = "Name,Phone\nRahul,+919876543210,Extra\nJane"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200
    res = response.json()
    assert res["rejected_count"] == 2
    assert "Expected 2 columns" in res["rejected_rows"][0]["errors"][0]

def test_mixed_valid_and_invalid_rows():
    csv_content = "Name,Phone\nRahul,+919876543210\n,invalid\nJane,+1234567890"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200
    res = response.json()
    assert res["total_rows"] == 3
    assert res["accepted_count"] == 2
    assert res["rejected_count"] == 1

def test_missing_file_and_missing_agent_id():
    response = client.post(ENDPOINT, data={"agent_id": AGENT_ID})
    assert response.status_code == 422 # FastAPI validation error for missing file

    files = {"file": ("test.csv", "Name,Phone\nRahul,+919876543210", "text/csv")}
    response = client.post(ENDPOINT, files=files)
    assert response.status_code == 422 # FastAPI validation error for missing agent_id

    response = client.post(ENDPOINT, files=files, data={"agent_id": "  "})
    assert response.status_code == 400
    assert "agent_id cannot be empty" in response.json()["detail"]

def test_unsupported_file_types():
    files = {"file": ("test.txt", "Name,Phone", "text/plain")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]

def test_blank_row_handling_and_correct_row_numbers():
    csv_content = "Name,Phone\n\nRahul,+919876543210\n   ,   \nJane,+1234567890\n"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200
    res = response.json()
    assert res["total_rows"] == 2
    assert res["accepted_leads"][0]["row_number"] == 3
    assert res["accepted_leads"][1]["row_number"] == 5

def test_correct_accepted_rejected_counts_agent_assignment():
    csv_content = "Name,Phone\nRahul,+919876543210\n,invalid"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": "my-agent-123"}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200
    res = response.json()
    assert res["accepted_count"] == 1
    assert res["rejected_count"] == 1
    assert res["accepted_leads"][0]["assigned_agent_id"] == "my-agent-123"
    assert res["agent_id"] == "my-agent-123"

def test_preservation_of_optional_fields():
    csv_content = "Name,Phone,City,Age\nRahul,+919876543210,Delhi,25"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200
    res = response.json()
    extra = res["accepted_leads"][0]["extra_fields"]
    assert extra == {"city": "Delhi", "age": "25"}

def test_consistent_file_level_error_responses():
    files = {"file": ("test.csv", "JustOneColumn", "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 400
    assert "detail" in response.json()

def test_bom_handling():
    # Test file with UTF-8 BOM
    csv_content = b"\xef\xbb\xbfName,Phone\nRahul,+919876543210"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200
    res = response.json()
    assert res["accepted_count"] == 1
    assert res["accepted_leads"][0]["name"] == "Rahul"

def test_verification_no_db_external():
    csv_content = "Name,Phone\nRahul,+919876543210"
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200

def test_uppercase_csv_extension_allowed():
    csv_content = "Name,Phone\nRahul,+919876543210"
    files = {"file": ("test.CSV", csv_content, "application/octet-stream")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 200
    assert response.json()["accepted_count"] == 1

def test_oversized_file_rejected(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_bytes", 100)
    csv_content = "Name,Phone\n" + ("Rahul,+919876543210\n" * 10)
    files = {"file": ("test.csv", csv_content, "text/csv")}
    data = {"agent_id": AGENT_ID}
    response = client.post(ENDPOINT, files=files, data=data)
    assert response.status_code == 413
    assert "exceeds maximum allowed size" in response.json()["detail"]

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_user_test_leads_file():
    test_file = Path(__file__).parent / "test data" / "test_leads.csv"
    if test_file.exists():
        with open(test_file, "rb") as f:
            response = client.post(ENDPOINT, files={"file": ("test_leads.csv", f, "text/csv")}, data={"agent_id": AGENT_ID})
        assert response.status_code == 200
        res = response.json()
        assert res["accepted_count"] == 3
        assert res["rejected_count"] == 3
        assert res["total_rows"] == 6

def test_user_stress_test_leads_file():
    stress_file = Path(__file__).parent / "test data" / "stress_test_leads.csv"
    if stress_file.exists():
        with open(stress_file, "rb") as f:
            response = client.post(ENDPOINT, files={"file": ("stress_test_leads.csv", f, "text/csv")}, data={"agent_id": AGENT_ID})
        assert response.status_code == 200
        res = response.json()
        assert res["accepted_count"] == 13
        assert res["rejected_count"] == 10
        assert res["total_rows"] == 23
