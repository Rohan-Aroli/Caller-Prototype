import io
import csv
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.config import settings
from backend.app.schemas.leads import LeadRecord
from backend.app.services.call_state import call_state_manager
from backend.app.services.csv_processor import parse_leads_csv, save_evaluated_leads_csv
from backend.app.services.telephony import telephony_provider, build_lead_greeting, build_lead_persona

client = TestClient(app)

@pytest.fixture(autouse=True)
def disable_signature_verification(monkeypatch):
    """Disable signature verification for unit test webhooks and expedite retries."""
    monkeypatch.setattr(settings, "VERIFY_TWILIO_SIGNATURE", False)
    monkeypatch.setattr(settings, "SERVER_DOMAIN", "test-domain.ngrok-free.app")
    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACmocktestaccountsid12345")
    monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", "mockauthtoken12345")
    monkeypatch.setattr(settings, "TWILIO_FROM_NUMBER", "+15551234567")
    monkeypatch.setattr(settings, "CALL_RETRY_DELAY_SECONDS", 0)

# =========================================================================
# 1. CSV Ingestion & Validation Tests
# =========================================================================

def test_parse_leads_csv_valid_3_columns():
    csv_text = (
        "name,number,reason for calling\n"
        "Alice Smith,+14155552671,Interested in Series A investment opportunity\n"
        "Bob Jones,+447911123456,Discuss voice AI enterprise partnership\n"
    )
    file_obj = io.StringIO(csv_text)
    leads = parse_leads_csv(file_obj, batch_id="batch-001")

    assert len(leads) == 2
    assert leads[0].name == "Alice Smith"
    assert leads[0].number == "+14155552671"
    assert leads[0].reason_for_calling == "Interested in Series A investment opportunity"
    assert leads[0].batch_id == "batch-001"
    assert leads[0].status == "pending"

    assert leads[1].name == "Bob Jones"
    assert leads[1].number == "+447911123456"

def test_parse_leads_csv_header_variations():
    csv_text = (
        "  Name  , Number , Reason For Calling \n"
        "Carol,+12025550199,Q3 Product Expansion Demo\n"
    )
    file_obj = io.StringIO(csv_text)
    leads = parse_leads_csv(file_obj)
    assert len(leads) == 1
    assert leads[0].name == "Carol"
    assert leads[0].number == "+12025550199"
    assert leads[0].reason_for_calling == "Q3 Product Expansion Demo"

def test_parse_leads_csv_missing_header_raises_422():
    csv_text = "name,number\nAlice,+14155552671\n"
    file_obj = io.StringIO(csv_text)
    with pytest.raises(Exception) as excinfo:
        parse_leads_csv(file_obj)
    assert "422" in str(excinfo.value)
    assert "reason for calling" in str(excinfo.value).lower()

def test_parse_leads_csv_missing_name_raises_422():
    csv_text = "name,number,reason for calling\n,+14155552671,Expansion discussion\n"
    file_obj = io.StringIO(csv_text)
    with pytest.raises(Exception) as excinfo:
        parse_leads_csv(file_obj)
    assert "422" in str(excinfo.value)
    assert "name" in str(excinfo.value).lower()

def test_parse_leads_csv_invalid_phone_raises_422():
    csv_text = "name,number,reason for calling\nAlice,invalid-number,Expansion discussion\n"
    file_obj = io.StringIO(csv_text)
    with pytest.raises(Exception) as excinfo:
        parse_leads_csv(file_obj)
    assert "422" in str(excinfo.value)
    assert "invalid" in str(excinfo.value).lower() or "e.164" in str(excinfo.value).lower()

def test_parse_leads_csv_missing_reason_raises_422():
    csv_text = "name,number,reason for calling\nAlice,+14155552671,\n"
    file_obj = io.StringIO(csv_text)
    with pytest.raises(Exception) as excinfo:
        parse_leads_csv(file_obj)
    assert "422" in str(excinfo.value)
    assert "reason for calling" in str(excinfo.value).lower()

# =========================================================================
# 2. LeadSessionManager State Tests
# =========================================================================

def test_lead_session_manager_lifecycle():
    async def _test():
        lead = LeadRecord(
            id="lead-test-01",
            batch_id="batch-test-01",
            name="Samantha",
            number="+14155559999",
            reason_for_calling="Series Seed Pitch"
        )

        # Register
        await call_state_manager.register_lead(lead)
        retrieved = await call_state_manager.get_lead_by_id("lead-test-01")
        assert retrieved is not None
        assert retrieved.name == "Samantha"

        # Bind CallSid
        await call_state_manager.bind_call_sid("lead-test-01", "CA99999mockcallsid")
        lead_by_call = await call_state_manager.get_lead_by_call_sid("CA99999mockcallsid")
        assert lead_by_call is not None
        assert lead_by_call.id == "lead-test-01"

        # Bind StreamSid
        await call_state_manager.bind_stream_to_lead("lead-test-01", "MZ88888mockstream")
        lead_by_stream = await call_state_manager.get_lead_by_stream_sid("MZ88888mockstream")
        assert lead_by_stream is not None
        assert lead_by_stream.name == "Samantha"

        # Transcripts
        await call_state_manager.append_transcript("MZ88888mockstream", "assistant", "Hi Samantha!")
        await call_state_manager.append_transcript("CA99999mockcallsid", "user", "Hello, tell me more.")

        transcript = await call_state_manager.get_transcript("lead-test-01")
        assert len(transcript) == 2
        assert transcript[0] == {"role": "assistant", "content": "Hi Samantha!"}
        assert transcript[1] == {"role": "user", "content": "Hello, tell me more."}

    import asyncio
    asyncio.run(_test())

# =========================================================================
# 3. Personalized Greeting & Persona Generation Tests
# =========================================================================

def test_lead_greeting_and_persona_generation():
    lead = LeadRecord(
        name="Vikram Singh",
        number="+919876543210",
        reason_for_calling="Discuss enterprise voice agent pilots"
    )

    greeting = build_lead_greeting(lead)
    assert "Hi Vikram Singh!" in greeting
    assert "Discuss enterprise voice agent pilots" in greeting

    persona = build_lead_persona(lead)
    assert "Vikram Singh" in persona
    assert "Discuss enterprise voice agent pilots" in persona
    assert "Core Objectives" in persona

# =========================================================================
# 4. API Endpoints: Upload 3-Column CSV & Download Results
# =========================================================================

def test_api_upload_3_column_csv_success():
    csv_content = (
        "name,number,reason for calling\n"
        "Emma Watson,+14155550111,Discuss AI telephony infrastructure\n"
        "David Clark,+14155550222,Explore investment in our Series A round\n"
    )
    files = {"file": ("prospects.csv", csv_content, "text/csv")}
    data = {"agent_id": "outbound-sales-bot"}

    with patch.object(telephony_provider, "trigger_call", return_value="CAtestmockcallsid123"):
        response = client.post("/api/v1/leads/upload-csv", files=files, data=data)

    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "processed"
    assert res["total_rows"] == 2
    assert res["accepted_count"] == 2
    assert res["batch_id"] is not None
    assert res["download_url"] is not None

    batch_id = res["batch_id"]

    # Test download endpoint
    dl_response = client.get(f"/api/v1/leads/download-results/{batch_id}")
    assert dl_response.status_code == 200
    assert "text/csv" in dl_response.headers["content-type"]
    content = dl_response.text
    assert "Emma Watson" in content
    assert "David Clark" in content
    assert "Investment_Probability_Score" in content

def test_api_upload_3_column_csv_with_invalid_row_returns_422():
    csv_content = (
        "name,number,reason for calling\n"
        "Emma Watson,+14155550111,Discuss AI telephony infrastructure\n"
        "Invalid Lead,not-a-number,Investment pitch\n"
    )
    files = {"file": ("prospects.csv", csv_content, "text/csv")}
    data = {"agent_id": "outbound-sales-bot"}

    response = client.post("/api/v1/leads/upload-csv", files=files, data=data)
    assert response.status_code == 422
    assert "invalid" in response.json()["detail"].lower() or "e.164" in response.json()["detail"].lower()

# =========================================================================
# 5. Twilio Status Callback & Retry Automation Tests
# =========================================================================

def test_status_callback_busy_schedules_retry():
    async def _test():
        lead = LeadRecord(
            id="lead-retry-01",
            batch_id="batch-retry-01",
            name="Arthur Dent",
            number="+441234567890",
            reason_for_calling="Interstellar logistics partnership",
            retry_count=0
        )
        await call_state_manager.register_lead(lead)
        await call_state_manager.bind_call_sid(lead.id, "CAretrytest01")

        with patch.object(telephony_provider, "trigger_call", return_value="CAnewretrycallsid999"):
            # Send status callback with 'busy'
            response = client.post(
                f"/api/v1/calls/status-callback?lead_id={lead.id}",
                data={"CallSid": "CAretrytest01", "CallStatus": "busy"}
            )
            assert response.status_code == 200
            assert response.json()["status"] == "received"

        updated = await call_state_manager.get_lead_by_id(lead.id)
        assert updated.retry_count == 1
        assert updated.status in ("retry_pending", "in_progress")

    import asyncio
    asyncio.run(_test())

def test_status_callback_exceed_max_retries_marks_unreachable():
    async def _test():
        lead = LeadRecord(
            id="lead-retry-max-01",
            batch_id="batch-retry-max-01",
            name="Ford Prefect",
            number="+441234567891",
            reason_for_calling="Publishing expansion",
            retry_count=settings.CALL_MAX_RETRIES  # Already at max retries
        )
        await call_state_manager.register_lead(lead)
        await call_state_manager.bind_call_sid(lead.id, "CAretrytest02")

        response = client.post(
            f"/api/v1/calls/status-callback?lead_id={lead.id}",
            data={"CallSid": "CAretrytest02", "CallStatus": "no-answer"}
        )
        assert response.status_code == 200

        updated = await call_state_manager.get_lead_by_id(lead.id)
        assert updated.status == "unreachable"
        assert updated.investment_score == 0
        assert "Max retries" in updated.evaluation_notes

    import asyncio
    asyncio.run(_test())

# =========================================================================
# 6. Post-Call LLM Evaluation & Scoring Tests
# =========================================================================

def test_post_call_evaluation_zero_user_engagement():
    async def _test():
        lead = LeadRecord(
            id="lead-eval-01",
            name="No Engagement Prospect",
            number="+14155550000",
            reason_for_calling="Series A Pitch"
        )
        # Transcript has only assistant greeting
        transcript = [{"role": "assistant", "content": "Hi there!"}]
        await telephony_provider.evaluate_lead_transcript(lead, transcript)

        assert lead.status == "completed"
        assert lead.investment_score == 0
        assert lead.interest_level == "Low"
        assert "Call answered but disconnected without engagement" in lead.evaluation_notes

    import asyncio
    asyncio.run(_test())

def test_post_call_evaluation_genuine_dialogue_mocked():
    async def _test():
        lead = LeadRecord(
            id="lead-eval-02",
            name="Engaged Investor",
            number="+14155550001",
            reason_for_calling="Seed investment round"
        )
        transcript = [
            {"role": "assistant", "content": "Hi Engaged Investor! Reaching out about our seed round."},
            {"role": "user", "content": "That sounds intriguing. Send over the deck, I'm interested in investing $250k."},
            {"role": "assistant", "content": "Fantastic, I will dispatch the investor memo immediately."}
        ]

        mock_response = MagicMock()
        mock_response.text = '{"investment_score": 92, "interest_level": "High", "evaluation_notes": "Very enthusiastic about participating with $250k ticket."}'

        mock_genai_model = MagicMock()
        mock_genai_model.generate_content_async = AsyncMock(return_value=mock_response)

        with patch("google.generativeai.GenerativeModel", return_value=mock_genai_model):
            await telephony_provider.evaluate_lead_transcript(lead, transcript)

        assert lead.status == "completed"
        assert lead.investment_score == 92
        assert lead.interest_level == "High"
        assert "Very enthusiastic" in lead.evaluation_notes

    import asyncio
    asyncio.run(_test())
