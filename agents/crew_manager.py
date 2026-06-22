from typing import List

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from pydantic import BaseModel, Field


class TimesheetEntry(BaseModel):
    employee_name: str = Field(..., description="Full name of the employee.")
    task_title: str = Field(
        ..., description="Short, action-oriented title of the task."
    )
    description: str = Field(..., description="Detailed description of the task scope.")
    day_type: str = Field(..., description="'Today' or 'Previous Day'")
    estimated_hours: float = Field(
        ..., description="Time estimate assigned to the task in hours."
    )
    start_time: str = Field(
        ..., description="Start time in HH:MM format, or empty string if Previous Day."
    )
    end_time: str = Field(
        ..., description="End time in HH:MM format, or empty string if Previous Day."
    )
    status: str = Field(..., description="Final processing status of the task entry.")


class TimesheetPayload(BaseModel):
    tasks: List[TimesheetEntry] = Field(
        ..., description="The complete array of timesheet entries."
    )


@CrewBase
class TimesheetAgent:
    """CrewaiTimesheetAgent crew"""

    agents: List[BaseAgent]
    tasks: List[Task]

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # ---------------------------------------------------------------------------
    # Agents
    # ---------------------------------------------------------------------------

    @agent
    def transcript_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["transcript_analyst"],
            verbose=False,
        )

    @agent
    def project_coordinator(self) -> Agent:
        return Agent(
            config=self.agents_config["project_coordinator"],
            verbose=False,
        )

    @agent
    def timesheet_exporter(self) -> Agent:
        return Agent(
            config=self.agents_config["timesheet_exporter"],
            verbose=False,
        )

    # ---------------------------------------------------------------------------
    # Tasks
    # ---------------------------------------------------------------------------

    @task
    def analyze_and_extract_transcript_task(self) -> Task:
        return Task(
            config=self.tasks_config["analyze_and_extract_transcript_task"],
            agent=self.transcript_analyst(),
        )

    @task
    def structure_and_schedule_tasks_task(self) -> Task:
        return Task(
            config=self.tasks_config["structure_and_schedule_tasks_task"],
            agent=self.project_coordinator(),
            context=[self.analyze_and_extract_transcript_task()],
        )

    @task
    def export_timesheet_json_task(self) -> Task:
        return Task(
            config=self.tasks_config["export_timesheet_json_task"],
            agent=self.timesheet_exporter(),
            context=[self.structure_and_schedule_tasks_task()],
            output_json=TimesheetPayload,
        )

    # ---------------------------------------------------------------------------
    # Crew
    # ---------------------------------------------------------------------------

    @crew
    def crew(self) -> Crew:
        """Assembles the CrewaiTimesheetAgent crew and runs tasks sequentially."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=False,
        )
