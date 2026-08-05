"""Fills the tables the main seed leaves empty.

Run after `scripts.seed`:  uv run python -m scripts.seed_extras

Everything here goes through the real services rather than writing rows
directly, so the seeded data obeys the same rules as anything a user creates —
journals balance, movements lock, media lands in the right folder. It is also
idempotent: each block checks whether its work is already done.

Photos are fetched from Unsplash at first run and cached under
`backend/media/seed_cache/`, so re-seeding does not re-download and the seed
still works without a network.
"""

import sys
import urllib.request
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

import app.modules  # noqa: F401
from app.common.enums import (
    MediaFolder,
    TrackingMode,
    UserRole,
)
from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.projects.models import Project
from app.modules.users.models import User

# Verified to resolve; each is a construction or building scene.
UNSPLASH = [
    ("photo-1541888946425-d81bb19240f5", "Site set up and hoarding in place"),
    ("photo-1503387762-592deb58ef4e", "Tower crane over the frame"),
    ("photo-1504307651254-35680f356dfd", "Steel frame going up"),
    ("photo-1512917774080-9991f1c4c750", "Block A elevation taking shape"),
    ("photo-1581094794329-c8112a89af12", "Services first fix underway"),
    ("photo-1523192193543-6e7296d960e4", "Formwork struck on the second floor"),
    ("photo-1487958449943-2429e8be8625", "Cladding started on the north face"),
    ("photo-1486406146926-c627a92ad1ab", "Curtain walling glazed"),
    ("photo-1466442929976-97f336a657be", "Roof level reached"),
    ("photo-1449824913935-59a10b8d2000", "External works and access road"),
    ("photo-1517089152318-42ec560349c0", "Reinforcement fixed to the raft"),
    ("photo-1516156008625-3a9d6067fab5", "Concrete pour in progress"),
    ("photo-1600585154340-be6161a56a0c", "Handover finish to the show unit"),
    ("photo-1600607687939-ce8a6c25118c", "Internal finishes complete"),
    ("photo-1621905251189-08b45d6a269e", "Plant on site for the deep dig"),
    ("photo-1541976590-713941681591", "Site office and welfare"),
]

CACHE = Path(settings.media_root) / "seed_cache"


def _photo(photo_id: str) -> bytes | None:
    """Cached so a re-seed costs nothing and works offline."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{photo_id}.jpg"
    if cached.exists():
        return cached.read_bytes()
    url = f"https://images.unsplash.com/{photo_id}?w=1400&q=80&fm=jpg"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
    except Exception as exc:  # offline, rate limited, anything
        print(f"  could not fetch {photo_id}: {exc}")
        return None
    cached.write_bytes(data)
    return data


def seed_media(db) -> None:
    from app.modules.media.models import MediaFile
    from app.modules.media.service import save_media

    if db.scalar(select(func.count()).select_from(MediaFile)):
        print("media: already seeded")
        return

    projects = list(db.scalars(select(Project).order_by(Project.code)))
    uploader = db.scalar(select(User).where(User.role == UserRole.site_manager))
    if not projects or uploader is None:
        print("media: nothing to attach to")
        return

    # Spread across the projects and backdated so the timeline has real depth
    # rather than every photo landing on today.
    added = 0
    for index, (photo_id, caption) in enumerate(UNSPLASH):
        content = _photo(photo_id)
        if content is None:
            continue
        project = projects[index % len(projects)]
        media = save_media(
            db,
            entity_type="project",
            entity_id=project.id,
            folder=MediaFolder.photos,
            caption=caption,
            filename=f"{photo_id}.jpg",
            content=content,
            media_type="image/jpeg",
            user_id=uploader.id,
        )
        # Walk backwards a few days at a time so the photo timeline groups into
        # distinct site visits instead of one enormous day.
        media.created_at = datetime.now(UTC) - timedelta(days=(len(UNSPLASH) - index) * 5)
        added += 1
    db.flush()
    print(f"media: {added} site photos attached")


def seed_comments(db) -> None:
    from app.modules.comments.models import Comment
    from app.modules.comments.schemas import CommentCreate
    from app.modules.comments.service import create as add_comment
    from app.modules.tasks.models import Task

    if db.scalar(select(func.count()).select_from(Comment)):
        print("comments: already seeded")
        return

    pm = db.scalar(select(User).where(User.role == UserRole.project_manager))
    site = db.scalar(select(User).where(User.role == UserRole.site_manager))
    tasks = list(db.scalars(select(Task).order_by(Task.created_at).limit(3)))
    if pm is None or site is None or not tasks:
        print("comments: nothing to talk about")
        return

    threads = [
        (tasks[0], pm, "Are we still clear to start Monday?"),
        (tasks[0], site, "Yes, rebar lands Friday and the gang is booked."),
        (tasks[-1], pm, "Check the levels against the setting-out drawing before you pour."),
    ]
    for task, author, body in threads:
        add_comment(db, "task", task.id, CommentCreate(body=body), author)

    project = db.scalar(select(Project).order_by(Project.code))
    if project is not None:
        add_comment(
            db,
            "project",
            project.id,
            CommentCreate(body="Client walked the site today and was happy with progress."),
            pm,
        )
    print("comments: seeded")


def seed_diary_labour(db) -> None:
    from app.modules.payroll.models import Worker
    from app.modules.site.models import SiteDiaryEntry, SiteDiaryLabour

    if db.scalar(select(func.count()).select_from(SiteDiaryLabour)):
        print("diary labour: already seeded")
        return

    entries = list(db.scalars(select(SiteDiaryEntry).order_by(SiteDiaryEntry.entry_date.desc()).limit(3)))
    workers = list(db.scalars(select(Worker).where(Worker.is_active.is_(True)).limit(4)))
    if not entries or not workers:
        print("diary labour: no diary or workers")
        return

    for entry in entries:
        for worker in workers:
            db.add(
                SiteDiaryLabour(
                    diary_entry_id=entry.id,
                    worker_id=worker.id,
                    quantity=Decimal("1"),
                    overtime_quantity=Decimal("0"),
                )
            )
        entry.labour_headcount = len(workers)
    db.flush()
    print(f"diary labour: {len(entries) * len(workers)} rows")


def seed_batches(db) -> None:
    from app.modules.inventory.models import StockBatch, StockItem
    from app.modules.inventory.schemas import GoodsInRequest
    from app.modules.inventory.service import goods_in

    if db.scalar(select(func.count()).select_from(StockBatch)):
        print("batches: already seeded")
        return

    admin = db.scalar(select(User).where(User.role == UserRole.admin))
    item = db.scalar(select(StockItem).where(StockItem.tracking_mode == TrackingMode.none))
    if admin is None or item is None:
        print("batches: no stock item to track")
        return

    # Switching an item to batch tracking is how a real store starts doing it.
    item.tracking_mode = TrackingMode.batch
    db.flush()
    for offset, batch_number in enumerate(("LOT-2026-114", "LOT-2026-127")):
        goods_in(
            db,
            item.id,
            GoodsInRequest(
                quantity=Decimal("40"),
                unit_cost=item.unit_cost or Decimal("12.00"),
                batch_number=batch_number,
                expiry_date=date.today() + timedelta(days=120 + offset * 45),
                reference=f"Batch delivery {batch_number}",
            ),
            admin.id,
        )
    print("batches: 2 lots received")


def seed_rfq_invites(db) -> None:
    from app.common.enums import RfqStatus
    from app.modules.procurement.models import Rfq, RfqInvite, Supplier
    from app.modules.procurement.rfq_portal import send_rfq

    if db.scalar(select(func.count()).select_from(RfqInvite)):
        print("rfq invites: already seeded")
        return

    rfq = db.scalar(select(Rfq).where(Rfq.status == RfqStatus.issued))
    suppliers = list(db.scalars(select(Supplier).limit(2)))
    officer = db.scalar(select(User).where(User.role == UserRole.procurement_officer))
    if rfq is None or not suppliers:
        print("rfq invites: no issued RFQ")
        return

    issued = send_rfq(db, rfq.id, [s.id for s in suppliers], 21, officer.id if officer else None)
    print(f"rfq invites: {len(issued)} sent — demo link: {issued[0][1]}")


def seed_user_invite(db) -> None:
    from app.modules.admin.models import UserInvite
    from app.modules.admin.schemas import InviteCreate
    from app.modules.admin.service import create_invite

    if db.scalar(select(func.count()).select_from(UserInvite)):
        print("user invites: already seeded")
        return

    admin = db.scalar(select(User).where(User.role == UserRole.admin))
    if admin is None:
        return
    _, raw = create_invite(
        db,
        InviteCreate(
            email="new.engineer@example.com", full_name="New Engineer", role=UserRole.site_manager
        ),
        admin.id,
    )
    print(f"user invites: 1 pending — accept at /accept-invite/{raw}")


def seed_trash(db) -> None:
    """One deleted record, so the Trash screen is not empty on a fresh install."""
    from app.modules.admin.models import DeletedRecord
    from app.modules.tasks.models import Task
    from app.modules.tasks.service import delete_task

    if db.scalar(select(func.count()).select_from(DeletedRecord)):
        print("trash: already seeded")
        return

    admin = db.scalar(select(User).where(User.role == UserRole.admin))
    task = db.scalar(select(Task).order_by(Task.created_at.desc()))
    if task is None:
        return
    delete_task(db, task.id, admin)
    print("trash: 1 deleted task")


def seed_activity(db) -> None:
    from app.modules.admin.models import ActivityLog
    from app.modules.admin.service import record

    if db.scalar(select(func.count()).select_from(ActivityLog)):
        print("activity: already seeded")
        return

    admin = db.scalar(select(User).where(User.role == UserRole.admin))
    project = db.scalar(select(Project).order_by(Project.code))
    if admin is None or project is None:
        return
    record(
        db,
        admin,
        "project_created",
        f"Set up {project.code} {project.name}",
        entity_type="project",
        entity_id=project.id,
        link_path=f"/projects/{project.id}",
    )
    print("activity: seeded")


def seed_ledger(db) -> None:
    """Posts the books from the operational data the main seed created."""
    from app.modules.accounting.service import ensure_chart, post_missing, trial_balance

    ensure_chart(db)
    posted = post_missing(db)
    balance = trial_balance(db)
    print(
        f"ledger: {posted} journals posted, "
        f"debits {balance['total_debit']} credits {balance['total_credit']}, "
        f"balanced={balance['balanced']}"
    )


def main() -> None:
    if settings.environment == "production":
        print("Refusing to run against production")
        sys.exit(1)

    db = SessionLocal()
    try:
        seed_media(db)
        seed_comments(db)
        seed_diary_labour(db)
        seed_batches(db)
        seed_rfq_invites(db)
        seed_user_invite(db)
        seed_activity(db)
        seed_trash(db)
        seed_ledger(db)
        db.commit()
        print("\nExtras complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
