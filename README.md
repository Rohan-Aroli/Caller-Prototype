# AI Calling Platform - CSV Lead Upload

This is the backend component of an AI calling platform, starting with a CSV ingestion endpoint.

## Setup

1. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the application

To run the backend server using `uvicorn`:

```bash
uvicorn backend.app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## API Documentation

FastAPI provides automatic API documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Running Tests

To run the automated tests, simply execute:

```bash
pytest backend/tests/
```
