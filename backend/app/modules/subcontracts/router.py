import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.common.enums import UserRole
from app.core.deps import CurrentUser, DbDep, require_roles
from app.core.exceptions import NotFoundError
from app.modules.subcontracts import service
from app.modules.subcontracts.models import (
    ComplianceDocument,
    ComplianceRequirement,
    Subcontract,
)
from app.modules.subcontracts.schemas import (
    CertifyRequest,
    ComplianceDocumentCreate,
    ComplianceDocumentRead,
    ComplianceStatus,
    ExpiringItem,
    MilestoneRead,
    RejectRequest,
    RequirementRead,
    RequirementUpdate,
    RetentionRegisterRow,
    RetentionReleaseCreate,
    RetentionReleaseRead,
    SubcontractCreate,
    SubcontractDetail,
    SubcontractRead,
    VendorStatusResult,
    VendorStatusUpdate,
)

router = APIRouter(tags=["subcontracts"])

vendor_admin = Depends(require_roles(UserRole.procurement_officer, UserRole.project_manager))
# Certifying a stage releases money, so it sits with the people who carry the
# job's cost rather than with whoever raised the package.
certifier = Depends(require_roles(UserRole.project_manager))


# --- Vendor compliance -------------------------------------------------------


@router.get("/suppliers/{supplier_id}/compliance", response_model=ComplianceStatus)
def get_compliance(supplier_id: uuid.UUID, db: DbDep) -> dict:
    """Where a supplier stands on paperwork, document by document."""
    return service.compliance_status(db, supplier_id)


@router.get(
    "/suppliers/{supplier_id}/compliance/documents",
    response_model=list[ComplianceDocumentRead],
)
def list_documents(supplier_id: uuid.UUID, db: DbDep) -> list[ComplianceDocumentRead]:
    return list(
        db.scalars(
            select(ComplianceDocument)
            .where(ComplianceDocument.supplier_id == supplier_id)
            .order_by(ComplianceDocument.doc_type, ComplianceDocument.expires_on.desc())
        )
    )


@router.post(
    "/suppliers/{supplier_id}/compliance/documents",
    response_model=ComplianceDocumentRead,
    status_code=201,
)
def add_document(
    supplier_id: uuid.UUID,
    body: ComplianceDocumentCreate,
    db: DbDep,
    user: CurrentUser,
    _=vendor_admin,
) -> ComplianceDocumentRead:
    service.compliance_status(db, supplier_id)  # proves the supplier exists
    doc = ComplianceDocument(
        supplier_id=supplier_id, **body.model_dump(), created_by=user.id
    )
    db.add(doc)
    db.flush()
    return doc


@router.delete("/compliance/documents/{document_id}", status_code=204)
def remove_document(document_id: uuid.UUID, db: DbDep, _=vendor_admin) -> None:
    doc = db.get(ComplianceDocument, document_id)
    if doc is None:
        raise NotFoundError("Document not found")
    db.delete(doc)


@router.post("/suppliers/{supplier_id}/vendor-status", response_model=VendorStatusResult)
def set_status(
    supplier_id: uuid.UUID,
    body: VendorStatusUpdate,
    db: DbDep,
    user: CurrentUser,
    _=vendor_admin,
) -> dict:
    """Approval is a decision about the relationship; it does not override
    lapsed paperwork."""
    supplier = service.set_vendor_status(db, supplier_id, body.vendor_status, user)
    return {"supplier_id": supplier.id, "vendor_status": supplier.vendor_status.value}


@router.get("/compliance/expiring", response_model=list[ExpiringItem])
def get_expiring(db: DbDep, days: int = 30) -> list[dict]:
    """Chased before it stops a job rather than after."""
    return service.expiring_soon(db, days)


@router.get("/compliance/requirements", response_model=list[RequirementRead])
def list_requirements(db: DbDep) -> list[dict]:
    service.ensure_requirements(db)
    return [
        {
            "doc_type": r.doc_type.value,
            "is_mandatory": r.is_mandatory,
            "warn_days": r.warn_days,
        }
        for r in db.scalars(select(ComplianceRequirement).order_by(ComplianceRequirement.doc_type))
    ]


@router.put("/compliance/requirements", response_model=list[RequirementRead])
def update_requirement(body: RequirementUpdate, db: DbDep, _=vendor_admin) -> list[dict]:
    service.ensure_requirements(db)
    row = db.scalar(
        select(ComplianceRequirement).where(ComplianceRequirement.doc_type == body.doc_type)
    )
    if row is None:
        row = ComplianceRequirement(doc_type=body.doc_type)
        db.add(row)
    row.is_mandatory = body.is_mandatory
    row.warn_days = body.warn_days
    db.flush()
    return list_requirements(db)


# --- Subcontracts ------------------------------------------------------------


def _read(contract: Subcontract) -> SubcontractRead:
    out = SubcontractRead.model_validate(contract)
    out.supplier_name = contract.supplier.name if contract.supplier else None
    return out


def _detail(db: DbDep, contract: Subcontract) -> SubcontractDetail:
    summary = service.subcontract_summary(db, contract.id)
    out = SubcontractDetail.model_validate(contract)
    out.supplier_name = contract.supplier.name if contract.supplier else None
    out.project_name = contract.project.name if contract.project else None
    out.certified = summary["certified"]
    out.retention_held = summary["retention_held"]
    out.retention_released = summary["retention_released"]
    out.retention_outstanding = summary["retention_outstanding"]
    out.net_payable = summary["net_payable"]
    out.remaining = summary["remaining"]
    out.releases = [
        RetentionReleaseRead.model_validate(row)
        for row in service.list_retention_releases(db, contract.id)
    ]
    # Shown on the package rather than only on the supplier, because whether
    # this vendor is still clear to work is a question about this job.
    out.vendor_compliant = service.compliance_status(db, contract.supplier_id)["is_compliant"]
    return out


@router.get("/projects/{project_id}/subcontracts", response_model=list[SubcontractRead])
def list_subcontracts(project_id: uuid.UUID, db: DbDep) -> list[SubcontractRead]:
    rows = db.scalars(
        select(Subcontract)
        .where(Subcontract.project_id == project_id)
        .order_by(Subcontract.doc_number)
    )
    return [_read(row) for row in rows]


@router.post(
    "/projects/{project_id}/subcontracts", response_model=SubcontractDetail, status_code=201
)
def create_subcontract(
    project_id: uuid.UUID,
    body: SubcontractCreate,
    db: DbDep,
    user: CurrentUser,
    _=vendor_admin,
) -> SubcontractDetail:
    contract = service.create_subcontract(db, project_id, body, user)
    return _detail(db, contract)


@router.get("/subcontracts/{subcontract_id}", response_model=SubcontractDetail)
def get_subcontract(subcontract_id: uuid.UUID, db: DbDep) -> SubcontractDetail:
    return _detail(db, service.get_subcontract(db, subcontract_id))


@router.post("/subcontracts/{subcontract_id}/award", response_model=SubcontractDetail)
def award_subcontract(
    subcontract_id: uuid.UUID, db: DbDep, user: CurrentUser, _=vendor_admin
) -> SubcontractDetail:
    """Refuses if the vendor is not approved or their mandatory papers have
    lapsed. This is where audit compliance stops being a claim."""
    return _detail(db, service.award(db, subcontract_id, user))


@router.post("/milestones/{milestone_id}/submit", response_model=MilestoneRead)
def submit_milestone(
    milestone_id: uuid.UUID, db: DbDep, user: CurrentUser, _=vendor_admin
) -> MilestoneRead:
    return service.submit_milestone(db, milestone_id, user)


@router.post("/milestones/{milestone_id}/certify", response_model=MilestoneRead)
def certify_milestone(
    milestone_id: uuid.UUID,
    body: CertifyRequest,
    db: DbDep,
    user: CurrentUser,
    _=certifier,
) -> MilestoneRead:
    """Books the cost to the job, owes the subcontractor the net, and holds the
    retention where it can be seen and released later."""
    return service.certify_milestone(db, milestone_id, body, user)


@router.post("/milestones/{milestone_id}/reject", response_model=MilestoneRead)
def reject_milestone(
    milestone_id: uuid.UUID,
    body: RejectRequest,
    db: DbDep,
    user: CurrentUser,
    _=certifier,
) -> MilestoneRead:
    return service.reject_milestone(db, milestone_id, body.reason, user)


@router.get("/subcontracts", response_model=list[SubcontractRead])
def list_all_subcontracts(
    db: DbDep, supplier_id: uuid.UUID | None = None
) -> list[SubcontractRead]:
    stmt = select(Subcontract).order_by(Subcontract.doc_number.desc())
    if supplier_id:
        stmt = stmt.where(Subcontract.supplier_id == supplier_id)
    return [_read(row) for row in db.scalars(stmt)]


# --- Retention ---------------------------------------------------------------


@router.get("/retention", response_model=list[RetentionRegisterRow])
def retention_register(db: DbDep) -> list[RetentionRegisterRow]:
    """Everything still held across every package, soonest to fall due first.

    Retention is other people's money sitting in a liability account. Nothing
    on a project screen shows it, so without this list it is only ever found
    when somebody rings up and asks for it.
    """
    return service.retention_register(db)


@router.post(
    "/subcontracts/{subcontract_id}/retention/release",
    response_model=RetentionReleaseRead,
    status_code=201,
)
def release_retention(
    subcontract_id: uuid.UUID,
    body: RetentionReleaseCreate,
    db: DbDep,
    user: CurrentUser,
    _=certifier,
) -> RetentionReleaseRead:
    """Moves held retention into what the subcontractor is owed."""
    return service.release_retention(db, subcontract_id, body, user)


@router.get(
    "/subcontracts/{subcontract_id}/retention", response_model=list[RetentionReleaseRead]
)
def list_releases(subcontract_id: uuid.UUID, db: DbDep) -> list[RetentionReleaseRead]:
    return service.list_retention_releases(db, subcontract_id)
