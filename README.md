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

## Full-Stack Development Setup

This repository now includes both the FastAPI backend and a Vite+React frontend, providing an end-to-end platform for CSV lead upload.

### Prerequisites

- Python >= 3.8
- Node.js >= 18
- npm

### Repository Structure

- `backend/` - Contains the FastAPI backend application.
- `frontend/` - Contains the React Vite frontend web application.
- `scripts/` - Scripts for project initialization.
- `tests/` - Backend tests.

### First-time Setup Instructions

To setup both the backend and frontend at once, execute the unified setup script from the repository root:

```bash
python scripts/setup.py
```
This script will:
1. Create a Python virtual environment for the backend (`.venv`).
2. Install Python backend dependencies.
3. Install Node.js frontend dependencies via `npm`.
4. Copy the frontend `.env.example` file to `.env`.

### Commands to Start the Backend

Run the backend server using `uvicorn`:

```bash
# On Linux/macOS:
.venv/bin/uvicorn backend.app.main:app --reload

# On Windows:
.venv\Scripts\uvicorn backend.app.main:app --reload
```
The backend API will run at `http://localhost:8000`.

### Commands to Start the Frontend

In a new terminal tab, navigate to the `frontend/` directory and run:

```bash
cd frontend
npm run dev --host
```
The frontend web app will typically be available at `http://localhost:5173`.

### Required Environment Variables

**Backend (Root `.env`)**:
A `.env` file is generated in the root directory during setup for Telephony & Gemini variables. You must populate it with your credentials:
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`: Get these from your Twilio Console.
- `GEMINI_API_KEY`: Get this from Google AI Studio.
- `SERVER_DOMAIN`: The public domain of your backend (e.g., `your-subdomain.ngrok-free.app`). Required for Twilio to reach your local server.

**Frontend**: A `.env` file is generated inside the `frontend` folder containing:
`VITE_API_BASE_URL=http://localhost:8000`
You can modify this if your backend listens on a different port.

### Real-Time Voice Calls

The backend now supports real-time voice calls by bridging Twilio WebSockets directly with the Gemini Multimodal Live API.

1. **Expose Localhost via ngrok**:
   To receive Twilio Webhooks on your local machine, run:
   ```bash
   ngrok http 8000
   ```
   Then set `SERVER_DOMAIN` in your root `.env` to the ngrok forwarding domain (e.g., `1234-abcd.ngrok-free.app`), without `http://` or `https://`.

2. **Triggering a Call**:
   You can trigger a call by sending a POST request to `/api/v1/calls/trigger-call`:
   ```json
   {
       "phone_number": "+1234567890"
   }
   ```
   When the user answers, Twilio requests TwiML from `/api/v1/calls/twiml`, which connects them to the `/api/v1/calls/media-stream` WebSocket for a real-time conversation powered by Gemini!

### CSV Upload Workflow

1. Navigate to the frontend UI (`http://localhost:5173`).
2. Enter an "Agent ID" in the text field.
3. Select a `.csv` file.
4. Click "Upload" to submit to the backend endpoint (`/api/v1/leads/upload-csv`).
5. Wait for the success or error response which will parse and validate CSV contents synchronously.

### Troubleshooting Guidance

- **Frontend doesn't connect to backend**: Ensure CORS is configured properly in `backend/app/main.py`. The backend should allow origins `http://localhost:5173`. Make sure the frontend `.env` points to the correct backend port.
- **Node.js dependencies missing**: Rerun `npm install` inside the `frontend` directory manually if the setup script fails.
- **Python environments misconfigured**: Ensure you are executing commands with `.venv/bin/python` or similar relative paths to isolate packages. If corrupted, remove the `.venv` folder and run `python scripts/setup.py` again.
