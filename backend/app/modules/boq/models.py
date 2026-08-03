import uuid
from decimal import Decimal

from sqlalchemy import (
    Computed,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.enums import BoqItemType, CostCategory
from app.common.models import AuditMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class BoqSection(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    __tablename__ = "boq_sections"
    __table_args__ = (UniqueConstraint("project_id", "code"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("boq_sections.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    items: Mapped[list["BoqItem"]] = relationship(
        back_populates="section", cascade="all, delete-orphan", order_by="BoqItem.sort_order"
    )
    children: Mapped[list["BoqSection"]] = relationship(
        cascade="all, delete-orphan", order_by="BoqSection.sort_order"
    )


class BoqItem(Base, UUIDPrimaryKeyMixin, TimestampMixin, AuditMixin):
    """Integration linchpin: future RFQ lines, PO lines and expenses FK to this table."""

    __tablename__ = "boq_items"
    __table_args__ = (UniqueConstraint("section_id", "item_code"),)

    section_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("boq_sections.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    item_code: Mapped[str] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(10))  # free text: m, m2, m3, kg, t, nr, sum...
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=Decimal("0"))
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    amount: Mapped[Decimal] = mapped_column(
        Numeric(16, 2), Computed("quantity * rate", persisted=True)
    )
    cost_category: Mapped[CostCategory] = mapped_column(
        Enum(CostCategory, name="cost_category", native_enum=True),
        default=CostCategory.material,
    )
    item_type: Mapped[BoqItemType] = mapped_column(
        Enum(BoqItemType, name="boq_item_type", native_enum=True),
        default=BoqItemType.original,
    )
    variation_ref: Mapped[str | None] = mapped_column(String(30))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    section: Mapped[BoqSection] = relationship(back_populates="items")
