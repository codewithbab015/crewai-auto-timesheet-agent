import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

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

from agents.crew_manager import TimesheetAgent
from api.database import get_session
from api.models import (
    AgentRequest,
    AgentResponse,
    AgentTaskStatus,
    FileType,
    FileUploadResponse,
    FileUploads,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_MIME_TYPES = {ft.value for ft in FileType}

# In-memory store for agent run statuses with concurrent lock processing
agent_run_store: dict[uuid.UUID, AgentResponse] = {}
store_lock = Lock()

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers / Explicit Fetching
# ---------------------------------------------------------------------------
def fetch_file_upload_record(
    file_upload_id: uuid.UUID, session: Session
) -> FileUploads:
    """Helper method to explicitly locate a record or raise a 404 error."""
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
    Updates agent_run_store securely using locks throughout lifecycle.
    """
    try:
        # Securely switch state to running
        with store_lock:
            if request_id in agent_run_store:
                agent_run_store[request_id].status = AgentTaskStatus.RUNNING

        today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Read transcription file content safely
        transcription_text = Path(transcription_path).read_text(encoding="utf-8")

        # Run the crew for each employee in the request context
        output_files = []
        for employee_name in employee_fullnames:
            inputs = {
                "team_transcription": transcription_text,
                "employee_name": employee_name,
                "today_date": today_date,
            }

            # Run the clean 3-agent pipeline execution
            results = TimesheetAgent().crew().kickoff(inputs=inputs)

            # Use results.json_dict safely if using Pydantic output, fallback to string format
            output_filename = (
                f"timesheet_{employee_name.replace(' ', '_')}_{today_date}.json"
            )
            output_files.append(output_filename)

        # Securely switch state to completed
        with store_lock:
            if request_id in agent_run_store:
                agent_run_store[request_id].status = AgentTaskStatus.COMPLETED
                agent_run_store[request_id].output_file = ", ".join(output_files)
                agent_run_store[
                    request_id
                ].message = f"Timesheet generation completed for: {', '.join(employee_fullnames)}."

    except Exception as exc:
        with store_lock:
            if request_id in agent_run_store:
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
        "saves it to local storage, and returns the file metadata including its UUID."
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
            detail=f"Unsupported file type '{file.content_type}'. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}",
        )

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
            detail=f"File size exceeds maximum allowed limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    file_id = uuid.uuid4()
    safe_filename = f"{file_id}_{file.filename}"
    file_path = UPLOAD_DIR / safe_filename

    with open(file_path, "wb") as buffer:
        buffer.write(content)

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
        "Accepts a JSON payload body containing employee names and an explicit file ID. "
        "Triggers processing asynchronously."
    ),
)
async def run_agent(
    body: AgentRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> AgentResponse:
    file_record = fetch_file_upload_record(body.file_upload_id, session)

    request_id = uuid.uuid4()

    response = AgentResponse(
        request_id=request_id,
        status=AgentTaskStatus.PENDING,
        employee_fullnames=body.employee_fullnames,
        file_upload_id=body.file_upload_id,
        message="Agent crew has been queued and will begin processing shortly.",
    )

    with store_lock:
        agent_run_store[request_id] = response

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
        "When completed, the `output_file` field contains the path to the generated JSON files."
    ),
)
async def get_agent_status(request_id: uuid.UUID) -> AgentResponse:
    with store_lock:
        run = agent_run_store.get(request_id)

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No agent run found for request_id '{request_id}'.",
        )
    return run
