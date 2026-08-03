from datetime import date, timedelta
from decimal import Decimal

from app.modules.projects.service import project_progress_pct
from tests.factories import make_project, make_task


def test_empty_project_is_zero(db):
    project = make_project(db)
    assert project_progress_pct(db, project.id) == 0.0


def test_explicit_weights(db):
    project = make_project(db)
    make_task(db, project, weight=Decimal("90"), progress_pct=100)
    make_task(db, project, weight=Decimal("10"), progress_pct=0)
    # 90% of the weight is done: never a naive (100+0)/2 = 50
    assert project_progress_pct(db, project.id) == 90.0


def test_duration_weighting_when_no_explicit_weight(db):
    project = make_project(db)
    start = date(2026, 1, 1)
    # 10-day task done, 30-day task untouched -> 10/40 = 25%
    make_task(
        db,
        project,
        planned_start=start,
        planned_end=start + timedelta(days=9),
        progress_pct=100,
    )
    make_task(
        db,
        project,
        planned_start=start,
        planned_end=start + timedelta(days=29),
        progress_pct=0,
    )
    assert project_progress_pct(db, project.id) == 25.0


def test_milestone_without_dates_gets_weight_one(db):
    project = make_project(db)
    make_task(db, project, planned_start=None, planned_end=None, progress_pct=100)
    assert project_progress_pct(db, project.id) == 100.0


def test_cancelled_tasks_excluded(db):
    project = make_project(db)
    make_task(db, project, weight=Decimal("50"), progress_pct=100)
    make_task(db, project, weight=Decimal("50"), progress_pct=0, status="cancelled")
    assert project_progress_pct(db, project.id) == 100.0
