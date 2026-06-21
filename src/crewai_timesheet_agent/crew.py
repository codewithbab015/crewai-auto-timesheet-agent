from typing import List

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task


@CrewBase
class CrewaiTimesheetAgent:
    """CrewaiTimesheetAgent crew"""

    agents: List[BaseAgent]
    tasks: List[Task]

    agents_config = "config/agents.yml"
    tasks_config = "config/tasks.yml"

    # ---------------------------------------------------------------------------
    # Agents
    # ---------------------------------------------------------------------------

    @agent
    def find_speaker(self) -> Agent:
        return Agent(
            config=self.agents_config["find_speaker"],
            verbose=True,
        )

    @agent
    def employee_detection(self) -> Agent:
        return Agent(
            config=self.agents_config["employee_detection"],
            verbose=True,
        )

    @agent
    def content_extraction(self) -> Agent:
        return Agent(
            config=self.agents_config["content_extraction"],
            verbose=True,
        )

    @agent
    def task_generation(self) -> Agent:
        return Agent(
            config=self.agents_config["task_generation"],
            verbose=True,
        )

    @agent
    def time_estimation(self) -> Agent:
        return Agent(
            config=self.agents_config["time_estimation"],
            verbose=True,
        )

    @agent
    def schedule(self) -> Agent:
        return Agent(
            config=self.agents_config["schedule"],
            verbose=True,
        )

    @agent
    def timesheet_export(self) -> Agent:
        return Agent(
            config=self.agents_config["timesheet_export"],
            verbose=True,
        )

    # ---------------------------------------------------------------------------
    # Tasks
    # ---------------------------------------------------------------------------

    @task
    def find_speaker_task(self) -> Task:
        return Task(
            config=self.tasks_config["find_speaker_task"],
            agent=self.find_speaker(),
        )

    @task
    def employee_detection_task(self) -> Task:
        return Task(
            config=self.tasks_config["employee_detection_task"],
            agent=self.employee_detection(),
            context=[self.find_speaker_task()],
        )

    @task
    def content_extraction_task(self) -> Task:
        return Task(
            config=self.tasks_config["content_extraction_task"],
            agent=self.content_extraction(),
            context=[self.employee_detection_task()],
        )

    @task
    def task_generation_task(self) -> Task:
        return Task(
            config=self.tasks_config["task_generation_task"],
            agent=self.task_generation(),
            context=[self.content_extraction_task()],
        )

    @task
    def time_estimation_task(self) -> Task:
        return Task(
            config=self.tasks_config["time_estimation_task"],
            agent=self.time_estimation(),
            context=[self.task_generation_task()],
        )

    @task
    def schedule_task(self) -> Task:
        return Task(
            config=self.tasks_config["schedule_task"],
            agent=self.schedule(),
            context=[self.time_estimation_task()],
        )

    @task
    def timesheet_export_task(self) -> Task:
        return Task(
            config=self.tasks_config["timesheet_export_task"],
            agent=self.timesheet_export(),
            context=[self.schedule_task()],
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
            verbose=True,
        )
