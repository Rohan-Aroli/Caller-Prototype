from fastapi import FastAPI
from backend.app.core.config import settings
from backend.app.api.routes import leads

app = FastAPI(title=settings.project_name)

app.include_router(leads.router, prefix=f"{settings.api_v1_str}/leads", tags=["leads"])
