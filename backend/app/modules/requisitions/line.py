"""One line of a material request, and what became of it.

A requisition line is where a shortage on site turns into buying. Somebody
asks for forty bags of cement; weeks later there is an order, a delivery and a
cost against a job, and the only thing tying those together is the line that
started it.

Tracing that is the whole point of giving it a page. The line itself holds
almost nothing — a description, a unit, a quantity — so everything worth
knowing has to be found by looking at what happened around it.

Matching is done on the description, deliberately and with its limits stated.
Requisition lines are typed by hand on site and rarely carry a stock or bill
reference, so an exact reference match would find nothing on real data. A
name match finds the right thing most of the time and is reported as a
likeness rather than a fact.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.modules.requisitions.models import Requisition, RequisitionItem


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


def line_detail(db: Session, item_id: uuid.UUID) -> dict:
    from app.modules.boq.models import BoqItem
    from app.modules.inventory.models import StockItem
    from app.modules.procurement.models import PoItem, PurchaseOrder, Rfq, RfqItem

    line = db.get(RequisitionItem, item_id)
    if line is None:
        raise NotFoundError("Requisition line not found")
    requisition = db.get(Requisition, line.requisition_id)

    wanted = _norm(line.description)

    # The bill line it was priced from, where one was named. Most are not.
    boq = db.get(BoqItem, line.boq_item_id) if line.boq_item_id else None

    # The item in the store that goes by this name. Matched on the description
    # because that is all a hand-typed line gives us.
    stock = None
    if wanted:
        stock = db.scalar(
            select(StockItem).where(func.lower(StockItem.name) == wanted).limit(1)
        )

    # Enquiries and orders raised for the same thing on the same job. Same
    # caveat: this is a likeness, not a link somebody recorded.
    enquiries = []
    if requisition is not None and wanted:
        rows = db.execute(
            select(Rfq, RfqItem)
            .join(RfqItem, RfqItem.rfq_id == Rfq.id)
            .where(Rfq.project_id == requisition.project_id)
        ).all()
        for rfq, rfq_item in rows:
            if _norm(rfq_item.description) == wanted:
                enquiries.append(
                    {
                        "rfq_id": rfq.id,
                        "doc_number": rfq.doc_number,
                        "title": rfq.title,
                        "status": rfq.status.value,
                    }
                )

    orders = []
    if requisition is not None and wanted:
        rows = db.execute(
            select(PurchaseOrder, PoItem)
            .join(PoItem, PoItem.po_id == PurchaseOrder.id)
            .where(PurchaseOrder.project_id == requisition.project_id)
        ).all()
        for order, po_item in rows:
            if _norm(po_item.description) == wanted:
                orders.append(
                    {
                        "purchase_order_id": order.id,
                        "doc_number": order.doc_number,
                        "status": order.status.value,
                        "supplier_id": order.supplier_id,
                        "supplier_name": order.supplier.name if order.supplier else None,
                        "quantity": Decimal(po_item.quantity),
                        "unit_price": Decimal(po_item.unit_price or 0),
                        "expected_delivery": order.expected_delivery,
                        "received_date": order.received_date,
                    }
                )

    ordered = sum((row["quantity"] for row in orders), Decimal("0"))
    return {
        "id": line.id,
        "requisition_id": line.requisition_id,
        "doc_number": requisition.doc_number if requisition else "",
        "requisition_status": requisition.status.value if requisition else "",
        "project_id": requisition.project_id if requisition else None,
        "needed_by": requisition.needed_by if requisition else None,
        "description": line.description,
        "unit": line.unit,
        "quantity": Decimal(line.quantity),
        "ordered_quantity": ordered,
        # Positive means more has been ordered than was asked for.
        "over_ordered": (ordered - Decimal(line.quantity)).quantize(Decimal("0.001")),
        "boq_item_id": boq.id if boq else None,
        "boq_description": boq.description if boq else None,
        "stock_item_id": stock.id if stock else None,
        "stock_code": stock.code if stock else None,
        "stock_on_hand": Decimal(stock.qty_on_hand) if stock else None,
        "enquiries": enquiries,
        "orders": orders,
        # Says how the enquiries and orders above were found, so nobody reads a
        # coincidence of wording as a recorded link.
        "matched_by": "reference" if boq else "description",
    }
