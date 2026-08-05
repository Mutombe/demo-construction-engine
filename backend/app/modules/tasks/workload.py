"""Who is carrying too much, over a window of days.

Deliberately built on what the data actually supports. There is no per-person
capacity anywhere in this system — no contracted hours, no availability
calendar — so inventing a "78% utilised" figure would be inventing the
denominator. What is real is: which open tasks a person is assigned, and which
days those tasks are live on. So the measure is concurrency, the count of open
tasks live on the same day, plus the hours actually booked against those tasks
once site starts naming them on timesheets.

Concurrency is the honest version of the question a PM is really asking, which
is "is anyone being asked to be in two places at once".
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import WorkStatus
from app.modules.payroll.models import Timesheet
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.modules.users.models import User

# More than this many tasks live on one day and the person is double-booked.
# A foreman genuinely runs two fronts at once; three is a warning.
DEFAULT_CONCURRENCY_LIMIT = 2

# Open means "still someone's problem".
OPEN_STATUSES = (WorkStatus.not_started, WorkStatus.in_progress, WorkStatus.blocked)


@dataclass
class PersonDay:
    day: date
    task_count: int
    over: bool


@dataclass
class PersonLoad:
    user_id: uuid.UUID | None
    full_name: str
    role: str | None
    open_tasks: int
    # Days inside the window on which at least one task is live
    busy_days: int
    peak_concurrency: int
    overloaded_days: int
    hours_booked: float
    next_free_day: date | None
    days: list[PersonDay] = field(default_factory=list)
    tasks: list[dict] = field(default_factory=list)


def _window_days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def workload(
    db: Session,
    start: date,
    end: date,
    project_id: uuid.UUID | None = None,
    limit: int = DEFAULT_CONCURRENCY_LIMIT,
) -> dict:
    """Per-person load across a date window.

    Tasks with no dates cannot be placed on a day, so they are counted in
    `open_tasks` and listed, but contribute nothing to concurrency — guessing a
    window for them would manufacture overload that does not exist.
    """
    stmt = (
        select(Task, Project.name, Project.code)
        .join(Project, Project.id == Task.project_id)
        .where(Task.status.in_(OPEN_STATUSES))
    )
    if project_id is not None:
        stmt = stmt.where(Task.project_id == project_id)
    rows = db.execute(stmt).all()

    people: dict[uuid.UUID | None, PersonLoad] = {}
    names = _assignee_names(db)
    days = _window_days(start, end)

    # user_id -> day -> count
    grid: dict[uuid.UUID | None, dict[date, int]] = {}

    for task, project_name, project_code in rows:
        key = task.assignee_id
        if key not in people:
            user = names.get(key)
            people[key] = PersonLoad(
                user_id=key,
                full_name=user[0] if user else "Unassigned",
                role=user[1] if user else None,
                open_tasks=0,
                busy_days=0,
                peak_concurrency=0,
                overloaded_days=0,
                hours_booked=0.0,
                next_free_day=None,
            )
            grid[key] = {}
        load = people[key]
        load.open_tasks += 1
        load.tasks.append(
            {
                "id": task.id,
                "name": task.name,
                "project_id": task.project_id,
                "project_name": project_name,
                "project_code": project_code,
                "status": task.status.value,
                "planned_start": task.planned_start,
                "planned_end": task.planned_end,
                "progress_pct": task.progress_pct,
                "is_scheduled": bool(task.planned_start and task.planned_end),
            }
        )
        if not (task.planned_start and task.planned_end):
            continue
        for day in days:
            if task.planned_start <= day <= task.planned_end:
                grid[key][day] = grid[key].get(day, 0) + 1

    hours = _booked_hours(db, start, end, project_id)

    for key, load in people.items():
        per_day = grid.get(key, {})
        load.days = [
            PersonDay(day=day, task_count=per_day.get(day, 0), over=per_day.get(day, 0) > limit)
            for day in days
        ]
        counted = [d for d in load.days if d.task_count > 0]
        load.busy_days = len(counted)
        load.peak_concurrency = max((d.task_count for d in load.days), default=0)
        load.overloaded_days = sum(1 for d in load.days if d.over)
        load.next_free_day = next((d.day for d in load.days if d.task_count == 0), None)
        load.hours_booked = float(hours.get(key, 0))
        # Busiest first: the point of the screen is who to take work off.
        load.tasks.sort(key=lambda t: (t["planned_start"] is None, t["planned_start"]))

    ordered = sorted(
        people.values(),
        key=lambda p: (
            p.user_id is None,  # unassigned sinks to the bottom
            -p.overloaded_days,
            -p.peak_concurrency,
            -p.open_tasks,
        ),
    )
    return {
        "start": start,
        "end": end,
        "concurrency_limit": limit,
        "people": ordered,
    }


def _assignee_names(db: Session) -> dict[uuid.UUID, tuple[str, str]]:
    return {
        row[0]: (row[1], row[2].value)
        for row in db.execute(select(User.id, User.full_name, User.role)).all()
    }


def _booked_hours(
    db: Session, start: date, end: date, project_id: uuid.UUID | None
) -> dict[uuid.UUID | None, float]:
    """Hours booked in the window, credited to the task's assignee.

    Timesheets belong to workers, who are not system users, so this cannot be
    keyed on who logged the time. Crediting the assignee of the named task is
    what makes it answer "how much work has actually gone into what this person
    owns". Rows with no task are skipped rather than spread around.
    """
    stmt = (
        select(Task.assignee_id, func.sum(Timesheet.quantity + Timesheet.overtime_quantity))
        .join(Task, Task.id == Timesheet.task_id)
        .where(Timesheet.work_date >= start, Timesheet.work_date <= end)
        .group_by(Task.assignee_id)
    )
    if project_id is not None:
        stmt = stmt.where(Timesheet.project_id == project_id)
    return {row[0]: float(row[1] or 0) for row in db.execute(stmt).all()}
