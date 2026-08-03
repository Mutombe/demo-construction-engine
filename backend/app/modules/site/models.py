import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import IssueSeverity, IssueStatus, WeatherCondition
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class SiteDiaryEntry(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """One canonical record per project per day; corrections are edits."""

    __tablename__ = "site_diary_entries"
    __table_args__ = (UniqueConstraint("project_id", "entry_date"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    entry_date: Mapped[date] = mapped_column(Date)
    weather: Mapped[WeatherCondition] = mapped_column(
        Enum(WeatherCondition, name="weather_condition", native_enum=True),
        default=WeatherCondition.sunny,
    )
    labour_headcount: Mapped[int] = mapped_column(Integer, default=0)
    plant_equipment: Mapped[str | None] = mapped_column(Text)
    work_done: Mapped[str] = mapped_column(Text)
    delays: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class SiteIssue(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    __tablename__ = "site_issues"
    __table_args__ = (Index("ix_site_issues_project_status", "project_id", "status"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[IssueSeverity] = mapped_column(
        Enum(IssueSeverity, name="issue_severity", native_enum=True),
        default=IssueSeverity.medium,
    )
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, name="issue_status", native_enum=True), default=IssueStatus.open
    )
    raised_date: Mapped[date] = mapped_column(Date, default=date.today)
    resolved_date: Mapped[date | None] = mapped_column(Date)
    resolution_notes: Mapped[str | None] = mapped_column(Text)
