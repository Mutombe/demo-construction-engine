from enum import StrEnum


class UserRole(StrEnum):
    admin = "admin"
    project_manager = "project_manager"
    site_manager = "site_manager"
    procurement_officer = "procurement_officer"
    viewer = "viewer"


class ProjectStatus(StrEnum):
    planning = "planning"
    active = "active"
    on_hold = "on_hold"
    completed = "completed"
    cancelled = "cancelled"


class WorkStatus(StrEnum):
    not_started = "not_started"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"
    cancelled = "cancelled"


class TaskPriority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class DependencyType(StrEnum):
    FS = "FS"  # finish-to-start
    SS = "SS"  # start-to-start
    FF = "FF"  # finish-to-finish
    SF = "SF"  # start-to-finish


class CostCategory(StrEnum):
    material = "material"
    labour = "labour"
    plant = "plant"
    subcontract = "subcontract"
    preliminaries = "preliminaries"
    other = "other"


class BoqItemType(StrEnum):
    original = "original"
    variation = "variation"
    omission = "omission"


class VariationStatus(StrEnum):
    """Lifecycle of a variation or omission on the BOQ.

    Only approved variations move the certifiable contract value — a variation
    the client has not signed off is not money you can invoice.
    """

    proposed = "proposed"
    approved = "approved"
    rejected = "rejected"


class CostSource(StrEnum):
    manual = "manual"
    expense = "expense"
    purchase_order = "purchase_order"
    invoice = "invoice"
    payroll = "payroll"
    inventory_issue = "inventory_issue"


class WeatherCondition(StrEnum):
    sunny = "sunny"
    cloudy = "cloudy"
    rain = "rain"
    storm = "storm"


class IssueSeverity(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IssueStatus(StrEnum):
    open = "open"
    resolved = "resolved"


class ExpenseCategory(StrEnum):
    materials = "materials"
    transport = "transport"
    fuel = "fuel"
    accommodation = "accommodation"
    meals = "meals"
    tools = "tools"
    other = "other"


class ExpenseStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class StockMovementType(StrEnum):
    goods_in = "goods_in"
    issue = "issue"
    adjustment = "adjustment"
    transfer = "transfer"


class TrackingMode(StrEnum):
    """How closely individual units of an item are tracked.

    `none` is the default and behaves exactly as inventory did before batches
    existed. `batch` suits anything with a shelf life — cement, admixtures,
    paint, sealants. `serial` is the same machinery with one unit per record,
    for plant and power tools.
    """

    none = "none"
    batch = "batch"
    serial = "serial"


class StockLocationKind(StrEnum):
    """Where stock physically sits.

    A site store belongs to a project; a central store and a plant yard do not.
    """

    store = "store"
    site = "site"
    yard = "yard"


class StocktakeStatus(StrEnum):
    counting = "counting"
    approved = "approved"
    cancelled = "cancelled"


class ValuationStatus(StrEnum):
    draft = "draft"
    issued = "issued"
    paid = "paid"
    cancelled = "cancelled"


class PoDestination(StrEnum):
    project = "project"
    store = "store"


class IngestionStatus(StrEnum):
    received = "received"
    failed = "failed"
    needs_info = "needs_info"
    drafted = "drafted"
    posted = "posted"
    rejected = "rejected"


class IngestionDocType(StrEnum):
    supplier_invoice = "supplier_invoice"
    expense_receipt = "expense_receipt"
    delivery_note = "delivery_note"
    supplier_quote = "supplier_quote"


class IngestionChannel(StrEnum):
    upload = "upload"


class MediaFolder(StrEnum):
    drawings = "drawings"
    contracts = "contracts"
    permits = "permits"
    photos = "photos"
    reports = "reports"
    other = "other"


class PayBasis(StrEnum):
    hourly = "hourly"
    daily = "daily"


class PayItemKind(StrEnum):
    allowance = "allowance"
    deduction = "deduction"


class PayRunStatus(StrEnum):
    draft = "draft"
    approved = "approved"


class RequisitionStatus(StrEnum):
    open = "open"
    actioned = "actioned"
    cancelled = "cancelled"


class RfqStatus(StrEnum):
    draft = "draft"
    issued = "issued"
    closed = "closed"


class QuoteStatus(StrEnum):
    received = "received"
    accepted = "accepted"
    rejected = "rejected"


class PoStatus(StrEnum):
    draft = "draft"
    issued = "issued"
    received = "received"
    cancelled = "cancelled"


class AccountType(StrEnum):
    asset = "asset"
    liability = "liability"
    equity = "equity"
    revenue = "revenue"
    expense = "expense"


class JournalStatus(StrEnum):
    draft = "draft"
    posted = "posted"
    reversed = "reversed"


class JournalSource(StrEnum):
    """What caused the journal. Manual is the only one a person writes."""

    manual = "manual"
    cost_entry = "cost_entry"
    valuation = "valuation"
    goods_in = "goods_in"
    reversal = "reversal"


class EquipmentCategory(StrEnum):
    excavator = "excavator"
    loader = "loader"
    grader = "grader"
    roller = "roller"
    tipper = "tipper"
    truck = "truck"
    crane = "crane"
    generator = "generator"
    pump = "pump"
    compressor = "compressor"
    light_vehicle = "light_vehicle"
    other = "other"


class EquipmentStatus(StrEnum):
    available = "available"
    on_site = "on_site"
    workshop = "workshop"
    standing = "standing"
    off_hired = "off_hired"
    disposed = "disposed"


class Ownership(StrEnum):
    owned = "owned"
    hired = "hired"


class MeterType(StrEnum):
    """Yellow plant runs on hours; vehicles run on distance. Mixing the two on
    one scale is how utilisation figures stop meaning anything."""

    hours = "hours"
    kilometres = "kilometres"


class MeterSource(StrEnum):
    manual = "manual"
    telematics = "telematics"
