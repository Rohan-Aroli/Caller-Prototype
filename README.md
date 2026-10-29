# AI Calling Platform - CSV Lead Upload

This is the backend component of an AI calling platform, starting with a CSV ingestion endpoint.

## Setup

To set up the project (create a virtual environment and install dependencies), simply run the setup script:

```bash
python scripts/setup.py
```

## Running the application

To run the backend server using `uvicorn`:

```bash
# On Linux/macOS:
.venv/bin/uvicorn backend.app.main:app --reload

# On Windows:
.venv\Scripts\uvicorn backend.app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## API Documentation

FastAPI provides automatic API documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Running Tests

To run the automated tests, simply execute:

```bash
# On Linux/macOS:
PYTHONPATH=$(pwd) .venv/bin/pytest backend/tests/

# On Windows:
set PYTHONPATH=%cd%
.venv\Scripts\pytest backend/tests/
```
