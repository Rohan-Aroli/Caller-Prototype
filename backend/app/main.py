from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.config import settings
from backend.app.api.routes import leads, calls

app = FastAPI(title=settings.project_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], # Since no specific frontend port is guaranteed, open up to avoid issues. Ideally it'd be localhost:5173, but let's stick to simple * or "http://localhost:5173" and we can instruct the user.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "project": settings.project_name}

app.include_router(leads.router, prefix=f"{settings.api_v1_str}/leads", tags=["leads"])
app.include_router(calls.router, prefix=f"{settings.api_v1_str}/calls", tags=["calls"])
