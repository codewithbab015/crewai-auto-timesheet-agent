import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr
from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class FileType(str, Enum):
    """Allowed transcript file types."""

    TXT = "text/plain"
    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ---------------------------------------------------------------------------
# Database Models (SQLModel — maps to DB table)
# ---------------------------------------------------------------------------
class FileUploads(SQLModel, table=True):
    """Stores metadata for uploaded transcription files."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    file_name: str = Field(
        ...,
        max_length=255,
        description="Original name of the uploaded file",
        index=True,
    )
    file_type: str = Field(
        ...,
        description="MIME type of the uploaded file e.g. text/plain",
    )
    file_size: int = Field(..., description="File size in bytes", index=True)
    file_path: str = Field(
        ..., description="Relative path or S3 key where the file is stored", index=True
    )
    uploaded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of when the file was uploaded",
        index=True,
    )


# ---------------------------------------------------------------------------
# Request Models (Pydantic — used in FastAPI route bodies)
# ---------------------------------------------------------------------------
class AgentRequest(BaseModel):
    """Request body for triggering the timesheet agent crew."""

    employee_fullnames: list[str] = Field(
        ...,
        description="List of full names to search for in the transcription",
    )
    email_address: Optional[EmailStr] = Field(
        default=None,
        description="Optional email address to send the generated timesheet to",
    )
    file_upload_id: uuid.UUID = Field(
        ...,
        description="UUID of the previously uploaded FileUploads record to process",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "employee_fullnames": ["Nhlanhla Baloyi", "Nhlamulo Nkuna"],
                "email_address": "nhlanhla.baloyi@zyrax.com",
                "file_upload_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            }
        }


# ---------------------------------------------------------------------------
# Response Models (Pydantic — returned by FastAPI routes)
# ---------------------------------------------------------------------------
class FileUploadResponse(BaseModel):
    """Returned after a successful file upload."""

    id: uuid.UUID
    file_name: str
    file_type: str
    file_size: int
    file_path: str
    uploaded_at: datetime

    class Config:
        from_attributes = True


class AgentTaskStatus(str, Enum):
    """Possible states for an agent run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentResponse(BaseModel):
    """Returned after triggering the timesheet agent crew."""

    request_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique ID for this agent run — use to poll for status",
    )
    status: AgentTaskStatus = Field(
        default=AgentTaskStatus.PENDING,
        description="Current status of the agent crew run",
    )
    employee_fullnames: list[str]
    file_upload_id: uuid.UUID
    message: str = Field(
        default="Agent crew has been queued and will begin processing shortly.",
    )
    output_file: Optional[str] = Field(
        default=None,
        description="Path or URL to the generated timesheet CSV once completed",
    )
