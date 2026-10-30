# AI Calling Platform - CSV Lead Upload

This is the backend component of an AI calling platform, featuring a resilient, high-throughput CSV lead ingestion and validation pipeline.

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

## API Documentation & Health Check

- Health Check: `http://localhost:8000/health`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Running Tests

To run the automated tests (`pytest.ini` automatically configures module resolution):

```bash
# On Linux/macOS:
.venv/bin/pytest

# On Windows:
.venv\Scripts\pytest
```
