from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from backend.app.schemas.leads import CsvProcessingResponse
from backend.app.services.csv_processor import process_csv
import io

router = APIRouter()

@router.post("/upload-csv", response_model=CsvProcessingResponse)
async def upload_csv(
    file: UploadFile = File(...),
    agent_id: str = Form(...)
):
    if not agent_id.strip():
        raise HTTPException(status_code=400, detail="agent_id cannot be empty.")

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing file.")

    if file.content_type not in ["text/csv", "application/vnd.ms-excel"]:
        # If it doesn't have a csv content type and doesn't end with .csv
        if not file.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="Unsupported file type.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty.")

    # Decode using utf-8-sig to handle optional BOM
    try:
        text_content = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded.")

    file_obj = io.StringIO(text_content)

    return process_csv(file_obj, agent_id)
