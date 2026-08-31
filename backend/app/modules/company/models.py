from decimal import Decimal

from sqlalchemy import Enum, Numeric, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.enums import PlantCostingMode
from app.common.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.core.database import Base


class CompanySettings(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Singleton row — the service layer always upserts/reads the single record."""

    __tablename__ = "company_settings"

    name: Mapped[str] = mapped_column(String(200), default="My Construction Company")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    vat_rate_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("15.00"))
    fiscal_year_start_month: Mapped[int] = mapped_column(SmallInteger, default=1)
    default_retention_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("10.00"))
    # Left on `direct` so an existing set of books keeps behaving as it did.
    # Switching to internal hire changes where plant costs land, which is a
    # decision for whoever owns the accounts, not a default.
    plant_costing_mode: Mapped[PlantCostingMode] = mapped_column(
        Enum(PlantCostingMode, name="plant_costing_mode", native_enum=True),
        default=PlantCostingMode.direct,
    )
