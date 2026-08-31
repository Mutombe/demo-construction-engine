import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.common.enums import EquipmentCategory, EquipmentStatus, UserRole
from app.common.pagination import PageParamsDep
from app.common.schemas import Page
from app.core.deps import CurrentUser, DbDep, require_roles
from app.core.exceptions import ConflictError, NotFoundError
from app.modules.fleet import plant, service
from app.modules.fleet.models import (
    Equipment,
    EquipmentCertificate,
    PlantRecharge,
    EquipmentAssignment,
    FuelLog,
    MaintenanceRecord,
    MaintenanceSchedule,
    MeterReading,
)
from app.modules.fleet.schemas import (
    AssetRow,
    AssignmentCreate,
    AssignmentRead,
    AvailabilityRow,
    CertificateCreate,
    CertificateRead,
    DepreciationResult,
    EquipmentCompliance,
    EquipmentCosts,
    EquipmentCreate,
    EquipmentRead,
    EquipmentUpdate,
    ExpiringCertificate,
    FuelLogCreate,
    FuelLogRead,
    MaintenanceCreate,
    MaintenanceRead,
    MeterReadingCreate,
    MeterReadingRead,
    RechargeLine,
    RechargeResult,
    RecoveryReport,
    RunRequest,
    ScheduleCreate,
    ScheduleRead,
    TelematicsImport,
    TelematicsImportResult,
)

router = APIRouter(tags=["fleet"])

# The yard is run by the site and plant side; procurement hires the machines.
fleet_write = Depends(
    require_roles(UserRole.project_manager, UserRole.site_manager, UserRole.procurement_officer)
)


def _read(machine: Equipment) -> EquipmentRead:
    out = EquipmentRead.model_validate(machine)
    out.supplier_name = machine.supplier.name if machine.supplier else None
    out.current_project_name = machine.project.name if machine.project else None
    return out


@router.get("/equipment", response_model=Page[EquipmentRead])
def list_equipment(
    db: DbDep,
    params: PageParamsDep,
    status: EquipmentStatus | None = None,
    category: EquipmentCategory | None = None,
    project_id: uuid.UUID | None = None,
    search: str | None = None,
    include_inactive: bool = False,
) -> Page[EquipmentRead]:
    stmt = select(Equipment)
    if not include_inactive:
        stmt = stmt.where(Equipment.is_active.is_(True))
    if status is not None:
        stmt = stmt.where(Equipment.status == status)
    if category is not None:
        stmt = stmt.where(Equipment.category == category)
    if project_id is not None:
        stmt = stmt.where(Equipment.current_project_id == project_id)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            Equipment.name.ilike(like)
            | Equipment.code.ilike(like)
            | Equipment.registration.ilike(like)
        )

    from sqlalchemy import func

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Equipment.code)
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
    )
    return Page(
        items=[_read(m) for m in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.post("/equipment", response_model=EquipmentRead, status_code=201)
def create_equipment(body: EquipmentCreate, db: DbDep, user: CurrentUser, _=fleet_write):
    if db.scalar(select(Equipment).where(Equipment.code == body.code)):
        raise ConflictError(f"{body.code} is already on the fleet")
    machine = Equipment(**body.model_dump(), created_by=user.id)
    # The meter it arrives on is also its first reading, so work done in
    # its first period has something to be measured from.
    machine.opening_meter = machine.current_meter
    db.add(machine)
    db.flush()
    return _read(machine)


@router.get("/equipment/{equipment_id}", response_model=EquipmentRead)
def get_equipment(equipment_id: uuid.UUID, db: DbDep) -> EquipmentRead:
    return _read(service.get_equipment(db, equipment_id))


@router.patch("/equipment/{equipment_id}", response_model=EquipmentRead)
def update_equipment(
    equipment_id: uuid.UUID, body: EquipmentUpdate, db: DbDep, _=fleet_write
) -> EquipmentRead:
    machine = service.get_equipment(db, equipment_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(machine, field, value)
    db.flush()
    return _read(machine)


# --- Meter and fuel ----------------------------------------------------------


@router.get("/equipment/{equipment_id}/readings", response_model=list[MeterReadingRead])
def list_readings(equipment_id: uuid.UUID, db: DbDep, limit: int = 100):
    service.get_equipment(db, equipment_id)
    return list(
        db.scalars(
            select(MeterReading)
            .where(MeterReading.equipment_id == equipment_id)
            .order_by(MeterReading.reading_date.desc())
            .limit(min(limit, 500))
        )
    )


@router.post("/equipment/{equipment_id}/readings", response_model=MeterReadingRead, status_code=201)
def create_reading(
    equipment_id: uuid.UUID, body: MeterReadingCreate, db: DbDep, user: CurrentUser, _=fleet_write
):
    return service.record_reading(db, equipment_id, body, user)


@router.get("/equipment/{equipment_id}/fuel", response_model=list[FuelLogRead])
def list_fuel(equipment_id: uuid.UUID, db: DbDep, limit: int = 100):
    service.get_equipment(db, equipment_id)
    return list(
        db.scalars(
            select(FuelLog)
            .where(FuelLog.equipment_id == equipment_id)
            .order_by(FuelLog.log_date.desc())
            .limit(min(limit, 500))
        )
    )


@router.post("/equipment/{equipment_id}/fuel", response_model=FuelLogRead, status_code=201)
def create_fuel(
    equipment_id: uuid.UUID, body: FuelLogCreate, db: DbDep, user: CurrentUser, _=fleet_write
):
    return service.record_fuel(db, equipment_id, body, user)


@router.get("/fleet/fuel-exceptions", response_model=list[dict])
def get_fuel_exceptions(db: DbDep, days: int = 90) -> list[dict]:
    """Fills well above a machine's own baseline. Worth a look, not an
    accusation: a blocked filter and a siphon look the same in the data."""
    return service.fuel_exceptions(db, days)


# --- Utilisation and maintenance ---------------------------------------------


@router.get("/fleet/utilisation", response_model=list[dict])
def get_utilisation(
    db: DbDep,
    start: date | None = None,
    end: date | None = None,
    project_id: uuid.UUID | None = None,
) -> list[dict]:
    end = end or date.today()
    start = start or (end - timedelta(days=29))
    return service.utilisation(db, start, end, project_id)


@router.get("/fleet/maintenance-due", response_model=list[dict])
def get_maintenance_due(db: DbDep) -> list[dict]:
    return service.maintenance_due(db)


@router.get("/fleet/summary", response_model=dict)
def get_fleet_summary(db: DbDep) -> dict:
    return service.fleet_summary(db)


@router.get("/equipment/{equipment_id}/schedules", response_model=list[ScheduleRead])
def list_schedules(equipment_id: uuid.UUID, db: DbDep):
    service.get_equipment(db, equipment_id)
    return list(
        db.scalars(
            select(MaintenanceSchedule).where(
                MaintenanceSchedule.equipment_id == equipment_id
            )
        )
    )


@router.post("/equipment/{equipment_id}/schedules", response_model=ScheduleRead, status_code=201)
def create_schedule(
    equipment_id: uuid.UUID, body: ScheduleCreate, db: DbDep, _=fleet_write
):
    service.get_equipment(db, equipment_id)
    if body.interval_meter is None and body.interval_days is None:
        from app.core.exceptions import ValidationFailedError

        raise ValidationFailedError(
            "A service needs an interval: hours, days, or both"
        )
    schedule = MaintenanceSchedule(equipment_id=equipment_id, **body.model_dump())
    db.add(schedule)
    db.flush()
    return schedule


@router.get("/equipment/{equipment_id}/maintenance", response_model=list[MaintenanceRead])
def list_maintenance(equipment_id: uuid.UUID, db: DbDep):
    service.get_equipment(db, equipment_id)
    return list(
        db.scalars(
            select(MaintenanceRecord)
            .where(MaintenanceRecord.equipment_id == equipment_id)
            .order_by(MaintenanceRecord.service_date.desc())
        )
    )


@router.post("/equipment/{equipment_id}/maintenance", response_model=MaintenanceRead, status_code=201)
def create_maintenance(
    equipment_id: uuid.UUID, body: MaintenanceCreate, db: DbDep, user: CurrentUser, _=fleet_write
):
    return service.record_maintenance(db, equipment_id, body, user)


# --- Deployment --------------------------------------------------------------


@router.get("/equipment/{equipment_id}/assignments", response_model=list[AssignmentRead])
def list_assignments(equipment_id: uuid.UUID, db: DbDep):
    service.get_equipment(db, equipment_id)
    return list(
        db.scalars(
            select(EquipmentAssignment)
            .where(EquipmentAssignment.equipment_id == equipment_id)
            .order_by(EquipmentAssignment.started_on.desc())
        )
    )


@router.post("/equipment/{equipment_id}/assign", response_model=AssignmentRead, status_code=201)
def assign_equipment(
    equipment_id: uuid.UUID, body: AssignmentCreate, db: DbDep, user: CurrentUser, _=fleet_write
):
    return service.assign(db, equipment_id, body, user)


@router.post("/equipment/{equipment_id}/release", response_model=EquipmentRead)
def release_equipment(
    equipment_id: uuid.UUID, db: DbDep, _=fleet_write, when: date | None = None
) -> EquipmentRead:
    return _read(service.release(db, equipment_id, when))


@router.get("/equipment/{equipment_id}/costs", response_model=EquipmentCosts)
def get_equipment_costs(equipment_id: uuid.UUID, db: DbDep, days: int = 365) -> EquipmentCosts:
    """Fuel, workshop and downtime for one machine, and the cost per hour run.

    The figure that decides keep-or-hire, and the one nobody has, because fuel
    sits in one system, the workshop in another and the hire invoice in a third.
    """
    return service.equipment_costs(db, equipment_id, days)


@router.post("/fleet/telematics/import", response_model=TelematicsImportResult)
def import_telematics(
    body: TelematicsImport, db: DbDep, user: CurrentUser, _=fleet_write
) -> TelematicsImportResult:
    """Take a period of readings and fills from a tracker or bowser export.

    Every row is applied on its own, so a file that is partly wrong still
    lands the part that is right, and each refusal comes back with its line
    number and its reason.
    """
    return service.import_telematics(db, body.rows, user)


# --- Statutory compliance ----------------------------------------------------


@router.get("/equipment/{equipment_id}/compliance", response_model=EquipmentCompliance)
def get_equipment_compliance(equipment_id: uuid.UUID, db: DbDep) -> EquipmentCompliance:
    """Whether this machine is legally able to work, document by document."""
    return plant.equipment_compliance(db, equipment_id)


@router.post(
    "/equipment/{equipment_id}/certificates",
    response_model=CertificateRead,
    status_code=201,
)
def add_certificate(
    equipment_id: uuid.UUID,
    body: CertificateCreate,
    db: DbDep,
    user: CurrentUser,
    _=fleet_write,
) -> CertificateRead:
    service.get_equipment(db, equipment_id)
    cert = EquipmentCertificate(
        equipment_id=equipment_id, **body.model_dump(), created_by=user.id
    )
    db.add(cert)
    db.flush()
    return cert


@router.get("/equipment/{equipment_id}/certificates", response_model=list[CertificateRead])
def list_certificates(equipment_id: uuid.UUID, db: DbDep) -> list[CertificateRead]:
    service.get_equipment(db, equipment_id)
    return list(
        db.scalars(
            select(EquipmentCertificate)
            .where(EquipmentCertificate.equipment_id == equipment_id)
            .order_by(EquipmentCertificate.cert_type, EquipmentCertificate.expires_on.desc())
        )
    )


@router.delete("/equipment/certificates/{certificate_id}", status_code=204)
def remove_certificate(certificate_id: uuid.UUID, db: DbDep, _=fleet_write) -> None:
    cert = db.get(EquipmentCertificate, certificate_id)
    if cert is None:
        raise NotFoundError("Certificate not found")
    db.delete(cert)


@router.get("/fleet/certificates/expiring", response_model=list[ExpiringCertificate])
def get_expiring_certificates(db: DbDep, days: int = 30) -> list[ExpiringCertificate]:
    """Chased before it grounds a machine rather than after."""
    return plant.expiring_certificates(db, days)


# --- Plant hire recharge -----------------------------------------------------


@router.post("/fleet/recharge", response_model=RechargeResult)
def run_recharge(
    body: RunRequest, db: DbDep, user: CurrentUser, _=fleet_write
) -> RechargeResult:
    """Charge every job for the plant it used that month.

    Refuses while the books are on direct plant costing, where fuel and
    repairs already reach the job — recharging as well would charge it twice.
    Safe to run again: what was already charged is left alone.
    """
    return plant.run_recharge(db, body.period_start, user)


@router.get("/fleet/recharges", response_model=list[RechargeLine])
def list_recharges(db: DbDep, project_id: uuid.UUID | None = None) -> list[RechargeLine]:
    stmt = select(PlantRecharge, Equipment).join(Equipment, Equipment.id == PlantRecharge.equipment_id)
    if project_id:
        stmt = stmt.where(PlantRecharge.project_id == project_id)
    return [
        RechargeLine(
            equipment_id=row.equipment_id,
            code=machine.code,
            project_id=row.project_id,
            units=row.units,
            rate=row.rate,
            amount=row.amount,
        )
        for row, machine in db.execute(stmt.order_by(PlantRecharge.period_start.desc())).all()
    ]


@router.get("/fleet/recovery", response_model=RecoveryReport)
def get_recovery(db: DbDep, start: date, end: date) -> RecoveryReport:
    """What the yard cost against what it charged out."""
    return plant.recovery(db, start, end)


# --- Depreciation and the asset register -------------------------------------


@router.post("/fleet/depreciation", response_model=DepreciationResult)
def run_depreciation(
    body: RunRequest, db: DbDep, user: CurrentUser, _=fleet_write
) -> DepreciationResult:
    """A month of wear, posted. Repeating a month changes nothing."""
    return plant.run_depreciation(db, body.period_start, user)


@router.get("/fleet/assets", response_model=list[AssetRow])
def get_asset_register(db: DbDep) -> list[AssetRow]:
    """What the plant is carried at, machine by machine."""
    return plant.asset_register(db)


@router.get("/fleet/availability", response_model=list[AvailabilityRow])
def get_availability(db: DbDep, start: date, end: date) -> list[AvailabilityRow]:
    """Time on a job against time able to work, and what broke."""
    return plant.availability(db, start, end)
