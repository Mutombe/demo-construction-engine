from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import DbDep, require_roles
from app.modules.company.models import CompanySettings
from app.modules.company.schemas import CompanySettingsRead, CompanySettingsUpdate

router = APIRouter(prefix="/company-settings", tags=["company"])


def _get_or_create(db) -> CompanySettings:
    settings = db.scalar(select(CompanySettings).limit(1))
    if settings is None:
        settings = CompanySettings()
        db.add(settings)
        db.flush()
    return settings


@router.get("", response_model=CompanySettingsRead)
def get_settings(db: DbDep) -> CompanySettingsRead:
    return CompanySettingsRead.model_validate(_get_or_create(db))


@router.patch(
    "",
    response_model=CompanySettingsRead,
    dependencies=[Depends(require_roles())],  # admin only
)
def update_settings(body: CompanySettingsUpdate, db: DbDep) -> CompanySettingsRead:
    settings = _get_or_create(db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    return CompanySettingsRead.model_validate(settings)
