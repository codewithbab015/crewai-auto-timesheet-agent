#!/usr/bin/env python
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

from crewai_timesheet_agent.crew import CrewaiTimesheetAgent

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


file_path = "/home/nbaloyi/research/crewai_timesheet_agent/uploads/bafef5e2-830b-45b5-bc6e-2d770d316748_daily_standup_20260619.txt"


def load_transcription(path: str) -> str:
    """Reads transcription text from a file path."""
    file = Path(path)
    if not file.exists():
        print(f"[ERROR] Transcription file not found: {path}")
        sys.exit(1)
    if not file.is_file():
        print(f"[ERROR] Path is not a file: {path}")
        sys.exit(1)
    return file.read_text(encoding="utf-8")


def run():
    """
    Run the crew.
    """

    today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    inputs = {
        "team_transcription": load_transcription(file_path),
        "employee_name": "Nhlanhla Baloyi",
        "today_date": today_date,
    }

    try:
        CrewaiTimesheetAgent().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


def train():
    """
    Train the crew for a given number of iterations.
    """
    today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    inputs = {
        "team_transcription": "AI LLMs",
        "employee_name": "Nhlanhla Baloyi",
        "today_date": today_date,
    }

    try:
        CrewaiTimesheetAgent().crew().train(
            n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs
        )

    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")
