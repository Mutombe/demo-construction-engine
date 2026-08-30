import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import (
    EquipmentCategory,
    EquipmentStatus,
    MeterSource,
    MeterType,
    Ownership,
)
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base

ZERO = Decimal("0")


class Equipment(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """A machine on the fleet, owned or hired.

    `current_meter` is a cached copy of the latest reading so a list of two
    hundred machines does not need a subquery per row. The readings are the
    source of truth, and the cache is only ever moved forward by one.
    """

    __tablename__ = "equipment"

    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[EquipmentCategory] = mapped_column(
        Enum(EquipmentCategory, name="equipment_category", native_enum=True), index=True
    )
    make: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(60))
    registration: Mapped[str | None] = mapped_column(String(30), index=True)
    serial_number: Mapped[str | None] = mapped_column(String(60))
    year: Mapped[int | None] = mapped_column(Integer)

    ownership: Mapped[Ownership] = mapped_column(
        Enum(Ownership, name="ownership", native_enum=True), default=Ownership.owned
    )
    # What an hour on this machine costs a job: the hire rate for hired plant,
    # an internal rate for owned, so the job carries plant cost either way.
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), index=True
    )

    status: Mapped[EquipmentStatus] = mapped_column(
        Enum(EquipmentStatus, name="equipment_status", native_enum=True),
        default=EquipmentStatus.available,
        index=True,
    )
    current_project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )

    meter_type: Mapped[MeterType] = mapped_column(
        Enum(MeterType, name="meter_type", native_enum=True), default=MeterType.hours
    )
    current_meter: Mapped[Decimal] = mapped_column(Numeric(12, 1), default=ZERO)
    # Litres per hour this machine is expected to burn. A baseline is what
    # makes an abnormal draw detectable rather than merely large.
    expected_burn_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))

    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    supplier = relationship("Supplier")
    project = relationship("Project")


class MeterReading(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """An hour-meter or odometer reading, from a person or a telematics feed.

    A meter only goes forward. A reading below the last one is a mis-key or a
    replaced meter, and accepting it silently would corrupt every utilisation
    and burn-rate figure, all of which are derived from the gaps between
    readings.
    """

    __tablename__ = "meter_readings"
    __table_args__ = (
        Index("ix_meter_readings_equipment_date", "equipment_id", "reading_date"),
    )

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    reading_date: Mapped[date] = mapped_column(Date, index=True)
    meter: Mapped[Decimal] = mapped_column(Numeric(12, 1))
    source: Mapped[MeterSource] = mapped_column(
        Enum(MeterSource, name="meter_source", native_enum=True), default=MeterSource.manual
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    # Where a feed reports it: the difference between a machine being switched
    # on and a machine doing work.
    idle_hours: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    notes: Mapped[str | None] = mapped_column(Text)


class FuelLog(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """Fuel issued to a machine.

    Carries the meter at the time of filling, because litres alone say
    nothing. Litres against the hours run since the last fill is the number
    that shows whether fuel went into the machine or somewhere else.
    """

    __tablename__ = "fuel_logs"
    __table_args__ = (Index("ix_fuel_logs_equipment_date", "equipment_id", "log_date"),)

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    log_date: Mapped[date] = mapped_column(Date, index=True)
    litres: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 1))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    total_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    stock_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stock_items.id", ondelete="SET NULL")
    )
    reference: Mapped[str | None] = mapped_column(String(60))
    operator: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)


class MaintenanceSchedule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A recurring service, due on meter or on days, whichever lands first."""

    __tablename__ = "maintenance_schedules"

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    interval_meter: Mapped[Decimal | None] = mapped_column(Numeric(10, 1))
    interval_days: Mapped[int | None] = mapped_column(Integer)
    last_done_meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 1))
    last_done_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MaintenanceRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """Work actually done, planned or otherwise.

    `downtime_hours` is what makes a breakdown visible as lost production
    rather than only as a repair bill.
    """

    __tablename__ = "maintenance_records"

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("maintenance_schedules.id", ondelete="SET NULL")
    )
    service_date: Mapped[date] = mapped_column(Date, index=True)
    meter: Mapped[Decimal | None] = mapped_column(Numeric(12, 1))
    description: Mapped[str] = mapped_column(Text)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    downtime_hours: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL")
    )
    reference: Mapped[str | None] = mapped_column(String(60))


class EquipmentAssignment(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """Where a machine was, and when.

    An open assignment has no end date. Kept as history rather than only as a
    pointer on the machine, so plant cost can be attributed to the job that
    actually held it during a period.
    """

    __tablename__ = "equipment_assignments"
    __table_args__ = (Index("ix_equipment_assignments_open", "equipment_id", "ended_on"),)

    equipment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    started_on: Mapped[date] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
