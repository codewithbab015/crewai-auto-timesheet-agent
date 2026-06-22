from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = "postgresql+psycopg://user:12345@localhost:5432/timesheet_agent.db"

engine = create_engine(DATABASE_URL, echo=True)


def create_db_and_tables() -> None:
    """Creates all tables defined in SQLModel metadata."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency — yields a database session per request."""
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
