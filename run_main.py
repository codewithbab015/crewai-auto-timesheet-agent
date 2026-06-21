from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import create_db_and_tables
from app.routers import router as agent_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Creates DB tables on startup."""
    create_db_and_tables()
    yield


app = FastAPI(
    title="Timesheet Agent API",
    description=(
        "FastAPI service that accepts standup transcription files, "
        "runs a CrewAI pipeline to extract and structure employee tasks, "
        "and generates timesheet CSV exports."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(agent_router, prefix="/api", tags=["Timesheet Agent"])
