import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlmodel import Session

from app.database import get_session
from app.models import (
    AgentRequest,
    AgentResponse,
    AgentTaskStatus,
    FileType,
    FileUploadResponse,
    FileUploads,
)
from src.crewai_timesheet_agent.crew import CrewaiTimesheetAgent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_MIME_TYPES = {ft.value for ft in FileType}

# In-memory store for agent run statuses.
# Replace with a database table or Redis for production.
agent_run_store: dict[uuid.UUID, AgentResponse] = {}

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
def get_file_upload_or_404(
    file_upload_id: uuid.UUID,
    session: Session = Depends(get_session),
) -> FileUploads:
    """Reusable dependency — fetches a FileUploads record or raises 404."""
    record = session.get(FileUploads, file_upload_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File upload with id '{file_upload_id}' not found.",
        )
    return record


# ---------------------------------------------------------------------------
# Background task — runs the CrewAI pipeline
# ---------------------------------------------------------------------------
def run_agent_crew(
    request_id: uuid.UUID,
    employee_fullnames: list[str],
    transcription_path: str,
) -> None:
    """
    Executes the CrewAI timesheet pipeline in the background.
    Updates agent_run_store with status throughout.
    """
    try:
        # Mark as running
        agent_run_store[request_id].status = AgentTaskStatus.RUNNING

        today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Read transcription file content
        transcription_text = Path(transcription_path).read_text(encoding="utf-8")

        # Run the crew for each employee in the request
        output_files = []
        for employee_name in employee_fullnames:
            inputs = {
                "team_transcription": transcription_text,
                "transcription": transcription_text,
                "employee_name": employee_name,
                "today_date": today_date,
            }
            CrewaiTimesheetAgent().crew().kickoff(inputs=inputs)
            output_files.append(
                f"timesheet_{employee_name.replace(' ', '_')}_{today_date}.csv"
            )

        # Mark as completed
        agent_run_store[request_id].status = AgentTaskStatus.COMPLETED
        agent_run_store[request_id].output_file = ", ".join(output_files)
        agent_run_store[
            request_id
        ].message = (
            f"Timesheet generation completed for: {', '.join(employee_fullnames)}."
        )

    except Exception as exc:
        agent_run_store[request_id].status = AgentTaskStatus.FAILED
        agent_run_store[request_id].message = f"Agent crew failed: {str(exc)}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a transcription file",
    description=(
        "Accepts a transcription file (txt, pdf or docx), validates it, "
        "saves it to local storage, and returns the file metadata including its UUID. "
        "Use the returned UUID as `file_upload_id` when calling POST /run-agent."
    ),
)
async def upload_transcription(
    file: UploadFile = File(..., description="Transcription file to upload"),
    session: Session = Depends(get_session),
) -> FileUploadResponse:
    # Validate MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{file.content_type}'. "
                f"Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
            ),
        )

    # Read file content and validate size
    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    # Save file to disk
    file_id = uuid.uuid4()
    safe_filename = f"{file_id}_{file.filename}"
    file_path = UPLOAD_DIR / safe_filename

    with open(file_path, "wb") as buffer:
        buffer.write(content)

    # Persist metadata to database
    upload_record = FileUploads(
        id=file_id,
        file_name=file.filename,
        file_type=file.content_type,
        file_size=file_size,
        file_path=str(file_path),
        uploaded_at=datetime.now(timezone.utc),
    )
    session.add(upload_record)
    session.commit()
    session.refresh(upload_record)

    return FileUploadResponse.model_validate(upload_record)


@router.post(
    "/run-agent",
    response_model=AgentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger the timesheet agent crew",
    description=(
        "Accepts a list of employee full names and a previously uploaded file UUID. "
        "Triggers the CrewAI pipeline asynchronously in the background. "
        "Returns a `request_id` which can be used to poll POST /status/{request_id}."
    ),
)
async def run_agent(
    body: AgentRequest,
    background_tasks: BackgroundTasks,
    file_record: FileUploads = Depends(get_file_upload_or_404),
) -> AgentResponse:
    request_id = uuid.uuid4()

    # Build initial pending response and store it
    response = AgentResponse(
        request_id=request_id,
        status=AgentTaskStatus.PENDING,
        employee_fullnames=body.employee_fullnames,
        file_upload_id=body.file_upload_id,
        message="Agent crew has been queued and will begin processing shortly.",
    )
    agent_run_store[request_id] = response

    # Queue background task
    background_tasks.add_task(
        run_agent_crew,
        request_id=request_id,
        employee_fullnames=body.employee_fullnames,
        transcription_path=file_record.file_path,
    )

    return response


@router.get(
    "/status/{request_id}",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Poll agent run status",
    description=(
        "Returns the current status of a previously triggered agent run. "
        "Status will be one of: pending, running, completed, or failed. "
        "When completed, the `output_file` field contains the path to the generated CSV."
    ),
)
async def get_agent_status(request_id: uuid.UUID) -> AgentResponse:
    run = agent_run_store.get(request_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No agent run found for request_id '{request_id}'.",
        )
    return run
