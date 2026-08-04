import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import DependencyType, WorkStatus
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class Task(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "wbs_code"),
        CheckConstraint("progress_pct BETWEEN 0 AND 100", name="progress_range"),
        Index("ix_tasks_project_status", "project_id", "status"),
        Index("ix_tasks_assignee_status", "assignee_id", "status"),
        Index("ix_tasks_project_planned_end", "project_id", "planned_end"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    phase_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("phases.id", ondelete="SET NULL"), index=True
    )
    wbs_code: Mapped[str | None] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[WorkStatus] = mapped_column(
        Enum(WorkStatus, name="work_status", native_enum=True), default=WorkStatus.not_started
    )
    progress_pct: Mapped[int] = mapped_column(SmallInteger, default=0)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    actual_start: Mapped[date | None] = mapped_column(Date)
    actual_end: Mapped[date | None] = mapped_column(Date)
    # Frozen copy of the approved programme; slippage is planned vs baseline.
    # Null until someone sets a baseline for the project.
    baseline_start: Mapped[date | None] = mapped_column(Date)
    baseline_end: Mapped[date | None] = mapped_column(Date)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    phase = relationship("Phase")
    assignee = relationship("User", foreign_keys=[assignee_id])
    predecessor_links: Mapped[list["TaskDependency"]] = relationship(
        foreign_keys="TaskDependency.successor_id",
        back_populates="successor",
        cascade="all, delete-orphan",
    )
    successor_links: Mapped[list["TaskDependency"]] = relationship(
        foreign_keys="TaskDependency.predecessor_id",
        back_populates="predecessor",
        cascade="all, delete-orphan",
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        CheckConstraint("predecessor_id != successor_id", name="no_self_dependency"),
        Index("ix_task_dependencies_successor", "successor_id"),
    )

    predecessor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    successor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    dep_type: Mapped[DependencyType] = mapped_column(
        Enum(DependencyType, name="dependency_type", native_enum=True),
        default=DependencyType.FS,
    )
    lag_days: Mapped[int] = mapped_column(Integer, default=0)

    predecessor: Mapped[Task] = relationship(
        foreign_keys=[predecessor_id], back_populates="successor_links"
    )
    successor: Mapped[Task] = relationship(
        foreign_keys=[successor_id], back_populates="predecessor_links"
    )
