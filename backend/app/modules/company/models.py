from decimal import Decimal

from sqlalchemy import Numeric, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

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
