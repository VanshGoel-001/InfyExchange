import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, aliased, joinedload, selectinload

from app.database import get_db
from app.dependencies import get_current_admin
from app.models.audit_log import AuditLog
from app.models.failed_email import FailedEmail
from app.models.interest import Interest
from app.models.listing import Listing
from app.models.need import Need
from app.models.report import Report
from app.models.user import User
from app.services import email_service
from app.services.rate_limit import admin_limiter, rate_limit_dependency
from app.utils.enums import InterestStatus, ListingStatus, NeedStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
    dependencies=[
        Depends(get_current_admin),
        Depends(rate_limit_dependency(
            admin_limiter,
            "admin",
            "Too many admin requests. Please slow down.",
        )),
    ],
)


def log_admin_action(
    db: Session,
    actor_id: int,
    action: str,
    target_type: str,
    target_id: str | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Record an immutable audit log entry for privileged admin actions."""
    try:
        log_entry = AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            ip_address=ip_address,
            details=json.dumps(details) if details else None,
            created_at=datetime.utcnow(),
        )
        db.add(log_entry)
        db.flush()
    except Exception as exc:
        logger.error(f"Failed to record audit log: {exc}")


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    total_listings: int
    active_listings: int
    total_needs: int
    active_needs: int
    total_interests: int
    accepted_interests: int


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None
    actor_name: str | None = None
    action: str
    target_type: str
    target_id: str | None
    ip_address: str | None
    details: str | None
    created_at: datetime


class UpdateUserStatusRequest(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


@router.get("/stats", response_model=AdminStats)
def get_admin_stats(db: Session = Depends(get_db)):
    total_users = db.scalar(select(func.count(User.id))) or 0
    active_users = db.scalar(select(func.count(User.id)).where(User.is_active == True)) or 0

    total_listings = db.scalar(select(func.count(Listing.id))) or 0
    active_listings = (
        db.scalar(select(func.count(Listing.id)).where(Listing.status == ListingStatus.ACTIVE)) or 0
    )

    total_needs = db.scalar(select(func.count(Need.id))) or 0
    active_needs = (
        db.scalar(select(func.count(Need.id)).where(Need.status == NeedStatus.ACTIVE)) or 0
    )

    total_interests = db.scalar(select(func.count(Interest.id))) or 0
    accepted_interests = (
        db.scalar(select(func.count(Interest.id)).where(Interest.status == InterestStatus.ACCEPTED))
        or 0
    )

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_listings": total_listings,
        "active_listings": active_listings,
        "total_needs": total_needs,
        "active_needs": active_needs,
        "total_interests": total_interests,
        "accepted_interests": accepted_interests,
    }


@router.get("/users")
def get_all_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(User).order_by(desc(User.created_at))
    if search:
        search_term = f"%{search.strip()}%"
        stmt = stmt.where((User.name.ilike(search_term)) | (User.email.ilike(search_term)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    users = db.scalars(stmt.offset(skip).limit(limit)).all()

    return {
        "total": total,
        "items": [
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "phone": u.phone,
                "role": u.role,
                "is_admin": u.is_admin,
                "is_active": u.is_active,
                "joining_date": str(u.joining_date) if u.joining_date else None,
                "created_at": u.created_at,
            }
            for u in users
        ],
    }


@router.patch("/users/{user_id}")
def update_user_status(
    user_id: int,
    payload: UpdateUserStatusRequest,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    target_user = db.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if target_user.id == current_admin.id and payload.is_admin is False:
        raise HTTPException(status_code=400, detail="Cannot revoke your own admin rights.")

    if target_user.id == current_admin.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account.")

    changes = {}
    if payload.is_active is not None and payload.is_active != target_user.is_active:
        changes["is_active"] = {"from": target_user.is_active, "to": payload.is_active}
        target_user.is_active = payload.is_active

    if payload.is_admin is not None and payload.is_admin != target_user.is_admin:
        changes["is_admin"] = {"from": target_user.is_admin, "to": payload.is_admin}
        target_user.is_admin = payload.is_admin

    if changes:
        log_admin_action(
            db=db,
            actor_id=current_admin.id,
            action="UPDATE_USER",
            target_type="USER",
            target_id=str(user_id),
            ip_address=request.client.host if request.client else None,
            details={"email": target_user.email, "changes": changes},
        )
        db.commit()

    return {"message": "User updated successfully", "user_id": user_id}


@router.get("/listings")
def get_all_listings(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: ListingStatus | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = (
        select(Listing)
        .options(joinedload(Listing.owner), selectinload(Listing.images))
        .order_by(desc(Listing.created_at))
    )

    if status_filter:
        stmt = stmt.where(Listing.status == status_filter)
    if search:
        stmt = stmt.where(Listing.title.ilike(f"%{search.strip()}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    listings = db.scalars(stmt.offset(skip).limit(limit)).unique().all()

    return {
        "total": total,
        "items": [
            {
                "id": l.id,
                "title": l.title,
                "category": l.category,
                "listing_type": l.listing_type,
                "price": l.price,
                "status": l.status,
                "location": l.location,
                "owner_id": l.owner_id,
                "owner_name": l.owner.name if l.owner else "Unknown",
                "owner_email": l.owner.email if l.owner else "Unknown",
                "created_at": l.created_at,
                "image_count": len(l.images),
            }
            for l in listings
        ],
    }


@router.patch("/listings/{listing_id}/status")
def change_listing_status(
    listing_id: int,
    status: ListingStatus,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    old_status = listing.status
    listing.status = status

    log_admin_action(
        db=db,
        actor_id=current_admin.id,
        action="UPDATE_LISTING_STATUS",
        target_type="LISTING",
        target_id=str(listing_id),
        ip_address=request.client.host if request.client else None,
        details={"title": listing.title, "old_status": old_status, "new_status": status},
    )
    db.commit()

    return {"message": "Listing status updated", "listing_id": listing_id, "status": status}


@router.delete("/listings/{listing_id}")
def admin_delete_listing(
    listing_id: int,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    listing = db.get(Listing, listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    title = listing.title
    db.delete(listing)

    log_admin_action(
        db=db,
        actor_id=current_admin.id,
        action="DELETE_LISTING",
        target_type="LISTING",
        target_id=str(listing_id),
        ip_address=request.client.host if request.client else None,
        details={"title": title},
    )
    db.commit()

    return {"message": "Listing removed by admin", "listing_id": listing_id}


@router.get("/needs")
def get_all_needs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: NeedStatus | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = (
        select(Need)
        .options(joinedload(Need.user))
        .order_by(desc(Need.created_at))
    )

    if status_filter:
        stmt = stmt.where(Need.status == status_filter)
    if search:
        stmt = stmt.where(Need.title.ilike(f"%{search.strip()}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    needs = db.scalars(stmt.offset(skip).limit(limit)).all()

    return {
        "total": total,
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "category": n.category,
                "need_type": n.need_type,
                "budget": n.budget,
                "status": n.status,
                "location": n.location,
                "user_id": n.user_id,
                "user_name": n.user.name if n.user else "Unknown",
                "user_email": n.user.email if n.user else "Unknown",
                "created_at": n.created_at,
            }
            for n in needs
        ],
    }


@router.delete("/needs/{need_id}")
def admin_delete_need(
    need_id: int,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    need = db.get(Need, need_id)
    if not need:
        raise HTTPException(status_code=404, detail="Need not found")

    title = need.title
    db.delete(need)

    log_admin_action(
        db=db,
        actor_id=current_admin.id,
        action="DELETE_NEED",
        target_type="NEED",
        target_id=str(need_id),
        ip_address=request.client.host if request.client else None,
        details={"title": title},
    )
    db.commit()

    return {"message": "Need removed by admin", "need_id": need_id}


@router.get("/audit-logs")
def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = (
        select(AuditLog)
        .options(joinedload(AuditLog.actor))
        .order_by(desc(AuditLog.created_at))
    )
    total = db.scalar(select(func.count(AuditLog.id))) or 0
    logs = db.scalars(stmt.offset(skip).limit(limit)).all()

    return {
        "total": total,
        "items": [
            {
                "id": log.id,
                "actor_id": log.actor_id,
                "actor_name": log.actor.name if log.actor else "System",
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "ip_address": log.ip_address,
                "details": log.details,
                "created_at": log.created_at,
            }
            for log in logs
        ],
    }


@router.get("/reports")
def get_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Chat reports filed by users, newest first. Read-only, so nothing to audit."""

    reporter = aliased(User)
    reported = aliased(User)

    total = db.scalar(select(func.count(Report.id))) or 0

    rows = db.execute(
        select(Report, reporter, reported, Listing.title)
        .join(reporter, reporter.id == Report.reporter_id)
        .join(reported, reported.id == Report.reported_user_id)
        .outerjoin(Interest, Interest.id == Report.interest_id)
        .outerjoin(Listing, Listing.id == Interest.listing_id)
        .order_by(desc(Report.created_at))
        .offset(skip)
        .limit(limit)
    ).all()

    return {
        "total": total,
        "items": [
            {
                "id": report.id,
                "reporter_name": reporter_user.name,
                "reported_user_id": reported_user.id,
                "reported_name": reported_user.name,
                "reported_email": reported_user.email,
                "listing_title": listing_title,
                "reason": report.reason,
                "created_at": report.created_at,
            }
            for report, reporter_user, reported_user, listing_title in rows
        ],
    }


@router.get("/failed-emails")
def get_failed_emails(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Emails the provider could not deliver, waiting for an admin to retry or discard them."""

    total = db.scalar(select(func.count(FailedEmail.id))) or 0
    rows = db.scalars(
        select(FailedEmail)
        .order_by(desc(FailedEmail.created_at))
        .offset(skip)
        .limit(limit)
    ).all()

    return {
        "total": total,
        "items": [
            {
                "id": row.id,
                "to_email": row.to_email,
                "subject": row.subject,
                "error": row.error,
                "attempts": row.attempts,
                "created_at": row.created_at,
                "last_attempt_at": row.last_attempt_at,
            }
            for row in rows
        ],
    }


@router.post("/failed-emails/{email_id}/retry")
async def retry_failed_email(
    email_id: int,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    record = db.get(FailedEmail, email_id)
    if not record:
        raise HTTPException(status_code=404, detail="Email not found")

    adapter = email_service.get_adapter()

    # With no provider configured the console adapter would "succeed" and the
    # row would be deleted without anything having been delivered.
    if isinstance(adapter, email_service.ConsoleEmailAdapter):
        raise HTTPException(
            status_code=409,
            detail="Email sending is not configured on this server, so there is nothing to retry.",
        )

    message = email_service.EmailMessage(
        to_email=record.to_email,
        to_name=record.to_name,
        subject=record.subject,
        html=record.html,
        reply_to_email=record.reply_to_email,
        reply_to_name=record.reply_to_name,
    )

    ip_address = request.client.host if request.client else None

    try:
        await adapter.send(message)
    except Exception as exc:
        logger.exception("Retry of failed email %s failed again.", email_id)

        record.attempts += 1
        record.last_attempt_at = datetime.utcnow()
        record.error = f"{type(exc).__name__}: {exc}"[:300]

        log_admin_action(
            db=db,
            actor_id=current_admin.id,
            action="RETRY_EMAIL",
            target_type="EMAIL",
            target_id=str(email_id),
            ip_address=ip_address,
            details={"subject": record.subject, "result": "failed"},
        )
        db.commit()

        raise HTTPException(
            status_code=502,
            detail="The email provider did not accept it again. Check the provider settings, then retry or discard.",
        ) from exc

    log_admin_action(
        db=db,
        actor_id=current_admin.id,
        action="RETRY_EMAIL",
        target_type="EMAIL",
        target_id=str(email_id),
        ip_address=ip_address,
        details={"subject": record.subject, "result": "sent"},
    )
    db.delete(record)
    db.commit()

    return {"message": "Email sent", "email_id": email_id}


@router.delete("/failed-emails/{email_id}")
def discard_failed_email(
    email_id: int,
    request: Request,
    current_admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    record = db.get(FailedEmail, email_id)
    if not record:
        raise HTTPException(status_code=404, detail="Email not found")

    log_admin_action(
        db=db,
        actor_id=current_admin.id,
        action="DISCARD_EMAIL",
        target_type="EMAIL",
        target_id=str(email_id),
        ip_address=request.client.host if request.client else None,
        details={"subject": record.subject},
    )
    db.delete(record)
    db.commit()

    return {"message": "Email discarded", "email_id": email_id}

