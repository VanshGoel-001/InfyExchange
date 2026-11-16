"""API tests: the record of removed listings and needs, and the reasons behind it.

Every way an item can disappear (owner, admin, expiry) writes one `removals` row in the same
transaction as the delete. An admin has to give a reason and the owner is told it.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import Listing, Need, Notification, Removal
from app.services.cleanup import cleanup_expired_data
from tests.conftest import auth_headers, make_user
from tests.support import add_listing, add_need, admin_delete

LISTINGS = "/api/listings"
NEEDS = "/api/needs"
ADMIN = "/api/admin"


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def _owner_delete(client, url, user, reason=None):
    kwargs = {"json": {"reason": reason}} if reason else {}
    return client.request("DELETE", url, headers=auth_headers(user), **kwargs)


@pytest.fixture()
def admin(db_session):
    return make_user(db_session, is_admin=True)


@pytest.fixture(autouse=True)
def no_cloudinary(monkeypatch):
    monkeypatch.setattr("app.routers.listings.delete_image", lambda public_id: None)
    monkeypatch.setattr("app.services.cleanup.delete_image", lambda public_id: None)


class TestOwnerRemoval:
    @pytest.mark.parametrize("reason", ["OWNER_SOLD", "OWNER_UNAVAILABLE", "OWNER_MISTAKE", "OWNER_DELETED"])
    def test_the_owners_reason_is_recorded(self, client, db_session, reason):
        """TC-API-REM-001 | AC-13.1 | T12 | positive | deleting your listing stores what it was, who you are and the reason you gave"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner, title="Yonex racket", price=450)
        listing_id = listing.id
        assert _owner_delete(client, f"{LISTINGS}/{listing_id}", owner, reason).status_code == 200
        (row,) = db_session.scalars(select(Removal)).all()
        assert (row.kind, row.item_id, row.title, row.category, row.item_type, row.amount) == (
            "LISTING", listing_id, "Yonex racket", "BADMINTON", "SELL", 450,
        )
        assert (row.owner_id, row.removed_by_id, row.reason, row.note) == (owner.id, owner.id, reason, None)

    def test_older_clients_send_no_reason(self, client, db_session):
        """TC-API-REM-002 | AC-13.1 | T12 | positive | a delete with no body (the previous SPA) still works and counts as OWNER_DELETED"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner)
        assert client.delete(f"{LISTINGS}/{listing.id}", headers=auth_headers(owner)).status_code == 200
        assert db_session.scalar(select(Removal.reason)) == "OWNER_DELETED"

    @pytest.mark.parametrize("reason", ["ADMIN_REMOVED", "EXPIRED", "SOMETHING", ""])
    def test_an_owner_cannot_claim_a_system_reason(self, client, db_session, reason):
        """TC-API-REM-003 | AC-13.1 | T12 | negative | only the four owner reasons are accepted; the listing stays"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner)
        response = client.request("DELETE", f"{LISTINGS}/{listing.id}", headers=auth_headers(owner), json={"reason": reason})
        assert response.status_code == 422
        assert _count(db_session, Listing) == 1 and _count(db_session, Removal) == 0

    def test_someone_elses_listing_is_refused_and_not_recorded(self, client, db_session):
        """TC-API-REM-004 | AC-13.1 | T12 | negative | a refused delete leaves no record"""
        listing = add_listing(db_session, make_user(db_session))
        assert _owner_delete(client, f"{LISTINGS}/{listing.id}", make_user(db_session), "OWNER_SOLD").status_code == 403
        assert _count(db_session, Removal) == 0 and _count(db_session, Listing) == 1

    def test_owner_removes_a_need(self, client, db_session):
        """TC-API-REM-005 | AC-13.1 | T12 | positive | a need removed by its owner is recorded with its type and budget"""
        owner = make_user(db_session)
        need = add_need(db_session, owner, title="Need a racket", budget=300)
        need_id = need.id
        assert _owner_delete(client, f"{NEEDS}/{need_id}", owner, "OWNER_MISTAKE").status_code == 200
        (row,) = db_session.scalars(select(Removal)).all()
        assert (row.kind, row.item_id, row.title, row.item_type, row.amount, row.reason) == (
            "NEED", need_id, "Need a racket", "BORROW", 300, "OWNER_MISTAKE",
        )


class TestAdminRemoval:
    def test_a_reason_is_required(self, client, db_session, admin):
        """TC-API-REM-010 | AC-12.5 | T12 | negative | no body, a blank reason, a too-short one and a too-long one are all refused and nothing is deleted"""
        listing = add_listing(db_session, make_user(db_session))
        url = f"{ADMIN}/listings/{listing.id}"
        headers = auth_headers(admin)
        assert client.delete(url, headers=headers).status_code == 422
        for bad in ("", "   ", "ab", "x" * 201):
            assert admin_delete(client, url, headers, bad).status_code == 422, repr(bad)
        assert _count(db_session, Listing) == 1 and _count(db_session, Removal) == 0

    def test_reason_boundaries(self, client, db_session, admin):
        """TC-API-REM-011 | AC-12.5 | T12 | boundary | 3 and 200 characters are accepted, after trimming spaces"""
        headers = auth_headers(admin)
        a = add_listing(db_session, make_user(db_session))
        b = add_listing(db_session, make_user(db_session))
        assert admin_delete(client, f"{ADMIN}/listings/{a.id}", headers, "  abc  ").status_code == 200
        assert admin_delete(client, f"{ADMIN}/listings/{b.id}", headers, "y" * 200).status_code == 200
        assert sorted(len(n or "") for n in db_session.scalars(select(Removal.note))) == [3, 200]

    def test_it_is_recorded_audited_and_the_owner_is_told(self, client, db_session, admin):
        """TC-API-REM-012 | AC-12.5, AC-13.1 | T12 | business | an admin removal writes the record with who and why, the Admin log with the reason, and a bell notice for the owner"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner, title="Fake designer shoes")
        listing_id = listing.id
        assert admin_delete(client, f"{ADMIN}/listings/{listing_id}", auth_headers(admin), "Looks like a scam").status_code == 200
        (row,) = db_session.scalars(select(Removal)).all()
        assert (row.reason, row.note, row.removed_by_id, row.owner_id) == ("ADMIN_REMOVED", "Looks like a scam", admin.id, owner.id)
        (notice,) = db_session.scalars(select(Notification).where(Notification.user_id == owner.id)).all()
        assert (notice.kind, notice.listing_title, notice.detail, notice.actor_id) == (
            "listing_removed_by_admin", "Fake designer shoes", "Looks like a scam", None,
        )

    def test_the_owner_sees_an_admin_not_a_name(self, client, db_session, admin):
        """TC-API-REM-013 | AC-09.1 | T10 | business | the bell item shows the reason and never names the admin"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner, title="Fake designer shoes")
        admin_delete(client, f"{ADMIN}/listings/{listing.id}", auth_headers(admin), "Looks like a scam")
        (item,) = client.get("/api/notifications", headers=auth_headers(owner)).json()["items"]
        assert (item["kind"], item["actor_name"], item["detail"], item["listing_title"]) == (
            "listing_removed_by_admin", None, "Looks like a scam", "Fake designer shoes",
        )
        assert admin.name not in str(item)

    def test_an_admin_removing_their_own_listing_is_not_notified(self, client, db_session, admin):
        """TC-API-REM-014 | AC-09.1 | T10 | boundary | nobody is told about something they did themselves"""
        listing = add_listing(db_session, admin)
        admin_delete(client, f"{ADMIN}/listings/{listing.id}", auth_headers(admin), "Cleaning up my own")
        assert _count(db_session, Notification) == 0 and _count(db_session, Removal) == 1

    def test_a_need_is_recorded_and_the_owner_is_told(self, client, db_session, admin):
        """TC-API-REM-015 | AC-12.6 | T12 | business | the same holds for needs"""
        owner = make_user(db_session)
        need = add_need(db_session, owner, title="Need a bat")
        admin_delete(client, f"{ADMIN}/needs/{need.id}", auth_headers(admin), "Asks for money")
        (row,) = db_session.scalars(select(Removal)).all()
        assert (row.kind, row.reason, row.note) == ("NEED", "ADMIN_REMOVED", "Asks for money")
        notice = db_session.scalar(select(Notification).where(Notification.user_id == owner.id))
        assert (notice.kind, notice.detail) == ("need_removed_by_admin", "Asks for money")

    def test_a_missing_item_is_a_404_and_records_nothing(self, client, db_session, admin):
        """TC-API-REM-016 | AC-12.5 | T12 | negative | removing something that does not exist leaves no record"""
        assert admin_delete(client, f"{ADMIN}/listings/999999", auth_headers(admin)).status_code == 404
        assert _count(db_session, Removal) == 0


class TestExpiry:
    def test_expired_items_are_recorded_by_the_cleanup(self, db_session):
        """TC-API-REM-020 | AC-14.1 | T15 | business | listings and needs removed at expiry are recorded as EXPIRED with nobody as the remover"""
        owner = make_user(db_session)
        gone = datetime.utcnow() - timedelta(minutes=1)
        add_listing(db_session, owner, title="Old racket", expires_at=gone)
        add_need(db_session, owner, title="Old need", expires_at=gone)
        add_listing(db_session, owner, title="Still live")
        cleanup_expired_data()
        db_session.expire_all()
        rows = db_session.scalars(select(Removal).order_by(Removal.kind)).all()
        assert [(r.kind, r.title, r.reason, r.removed_by_id, r.owner_id) for r in rows] == [
            ("LISTING", "Old racket", "EXPIRED", None, owner.id),
            ("NEED", "Old need", "EXPIRED", None, owner.id),
        ]
        assert _count(db_session, Listing) == 1 and _count(db_session, Need) == 0

    def test_old_records_are_deleted_after_the_retention_period(self, db_session):
        """TC-API-REM-021 | AC-14.1 | T15 | boundary | a record older than the retention period goes; one inside it stays"""
        now = datetime.utcnow()
        days = settings.removal_retention_days
        for title, age in (("old", days + 1), ("recent", days - 1)):
            db_session.add(
                Removal(kind="LISTING", item_id=1, title=title, reason="OWNER_SOLD", created_at=now - timedelta(days=age))
            )
        db_session.commit()
        cleanup_expired_data()
        db_session.expire_all()
        assert [r.title for r in db_session.scalars(select(Removal))] == ["recent"]


class TestAdminList:
    def _seed(self, client, db_session, admin):
        ann = make_user(db_session)
        ann.name = "Ann Rao"
        ben = make_user(db_session)
        ben.name = "Ben Das"
        db_session.commit()
        sold = add_listing(db_session, ann, title="Cricket bat")
        scam = add_listing(db_session, ben, title="Racket deal")
        need = add_need(db_session, ben, title="Need a ball")
        _owner_delete(client, f"{LISTINGS}/{sold.id}", ann, "OWNER_SOLD")
        admin_delete(client, f"{ADMIN}/listings/{scam.id}", auth_headers(admin), "Scam")
        admin_delete(client, f"{ADMIN}/needs/{need.id}", auth_headers(admin), "Spam")
        add_listing(db_session, ann, title="Expired one", expires_at=datetime.utcnow() - timedelta(minutes=1))
        cleanup_expired_data()

    def test_newest_first_with_names(self, client, db_session, admin):
        """TC-API-REM-030 | AC-12.5 | T12 | positive | the list shows what, whose, who removed it, when and why, newest first"""
        self._seed(client, db_session, admin)
        body = client.get(f"{ADMIN}/removals", headers=auth_headers(admin)).json()
        assert body["total"] == 4
        assert [i["title"] for i in body["items"]] == ["Expired one", "Need a ball", "Racket deal", "Cricket bat"]
        by_title = {i["title"]: i for i in body["items"]}
        assert (by_title["Cricket bat"]["owner_name"], by_title["Cricket bat"]["removed_by_name"], by_title["Cricket bat"]["reason"]) == (
            "Ann Rao", "Ann Rao", "OWNER_SOLD",
        )
        assert (by_title["Racket deal"]["removed_by_name"], by_title["Racket deal"]["note"]) == (admin.name, "Scam")
        assert (by_title["Expired one"]["removed_by_name"], by_title["Expired one"]["reason"]) == (None, "EXPIRED")
        assert {"id", "kind", "item_id", "category", "item_type", "amount", "owner_id", "removed_by_id", "created_at"} <= set(body["items"][0])

    def test_no_contact_details_in_the_list(self, client, db_session, admin):
        """TC-API-REM-031 | AC-12.5 | T12 | negative | the removal list carries no email or phone"""
        self._seed(client, db_session, admin)
        text = client.get(f"{ADMIN}/removals", headers=auth_headers(admin)).text
        assert "@gmail.com" not in text and "phone" not in text and "email" not in text

    def test_filters(self, client, db_session, admin):
        """TC-API-REM-032 | AC-12.5 | T12 | positive | kind, reason and a title or owner search narrow the list"""
        self._seed(client, db_session, admin)
        headers = auth_headers(admin)

        def titles(**params):
            return [i["title"] for i in client.get(f"{ADMIN}/removals", params=params, headers=headers).json()["items"]]

        assert titles(kind="NEED") == ["Need a ball"]
        assert titles(reason="OWNER_SOLD") == ["Cricket bat"]
        assert sorted(titles(reason="ADMIN_REMOVED")) == ["Need a ball", "Racket deal"]
        assert titles(search="racket") == ["Racket deal"]
        assert sorted(titles(search="ben")) == ["Need a ball", "Racket deal"]
        assert titles(kind="LISTING", reason="EXPIRED") == ["Expired one"]

    @pytest.mark.parametrize("params, expected", [({"kind": "OTHER"}, 422), ({"reason": "NOPE"}, 422), ({"limit": 0}, 422), ({"limit": 101}, 422), ({"limit": 100}, 200)])
    def test_parameter_boundaries(self, client, admin, params, expected):
        """TC-API-REM-033 | AC-12.5 | T12 | boundary | unknown kind or reason and limits outside 1-100 are refused"""
        assert client.get(f"{ADMIN}/removals", params=params, headers=auth_headers(admin)).status_code == expected

    def test_pagination_keeps_the_full_total(self, client, db_session, admin):
        """TC-API-REM-034 | AC-12.5 | T12 | boundary | limit and skip page the list while total counts everything"""
        self._seed(client, db_session, admin)
        page = client.get(f"{ADMIN}/removals", params={"limit": 2, "skip": 3}, headers=auth_headers(admin)).json()
        assert page["total"] == 4 and len(page["items"]) == 1

    def test_members_and_visitors_are_refused(self, client, db_session):
        """TC-API-REM-035 | AC-12.1 | T12 | negative | only admins can read it"""
        assert client.get(f"{ADMIN}/removals", headers=auth_headers(make_user(db_session))).status_code == 403
        assert client.get(f"{ADMIN}/removals").status_code in (401, 403)

    def test_an_owner_who_left_still_shows_as_a_blank_name(self, client, db_session, admin):
        """TC-API-REM-036 | AC-12.5 | T12 | boundary | when the owner's account is gone the row still lists, with no owner name"""
        db_session.add(Removal(kind="LISTING", item_id=9, title="Orphan", reason="EXPIRED", owner_id=None, created_at=datetime.utcnow()))
        db_session.commit()
        (item,) = client.get(f"{ADMIN}/removals", headers=auth_headers(admin)).json()["items"]
        assert (item["title"], item["owner_name"], item["owner_id"]) == ("Orphan", None, None)


class TestAdminRemovalSideEffects:
    def test_images_are_deleted_and_enquirers_are_told(self, client, db_session, admin, no_cloudinary_on_admin_delete):
        """TC-API-REM-040 | AC-12.5, AC-09.1 | T12 | business | an admin removal deletes the listing's Cloudinary images and tells everyone with an open enquiry"""
        from tests.support import add_image, add_interest
        from app.utils.enums import InterestStatus

        owner, waiting, chatting, declined = (make_user(db_session) for _ in range(4))
        listing = add_listing(db_session, owner, title="Gone soon")
        add_image(db_session, listing, public_id="pid-a")
        add_interest(db_session, listing, waiting)
        add_interest(db_session, listing, chatting, status=InterestStatus.ACCEPTED)
        add_interest(db_session, listing, declined, status=InterestStatus.REJECTED)
        assert admin_delete(client, f"{ADMIN}/listings/{listing.id}", auth_headers(admin)).status_code == 200
        assert no_cloudinary_on_admin_delete == ["pid-a"]
        told = {n.user_id: n.kind for n in db_session.scalars(select(Notification))}
        assert told == {owner.id: "listing_removed_by_admin", waiting.id: "enquiry_closed", chatting.id: "enquiry_closed"}

    def test_a_cloudinary_outage_does_not_block_the_removal(self, client, db_session, admin, monkeypatch):
        """TC-API-REM-041 | AC-12.5 | T09 | negative | when Cloudinary fails the listing is still removed, by an admin or by its owner"""
        from tests.support import add_image

        def boom(public_id):
            raise RuntimeError("simulated Cloudinary outage")

        monkeypatch.setattr("app.routers.admin.delete_image", boom)
        monkeypatch.setattr("app.routers.listings.delete_image", boom)
        owner = make_user(db_session)
        first, second = add_listing(db_session, owner), add_listing(db_session, owner)
        add_image(db_session, first)
        add_image(db_session, second)
        assert admin_delete(client, f"{ADMIN}/listings/{first.id}", auth_headers(admin)).status_code == 200
        assert client.delete(f"{LISTINGS}/{second.id}", headers=auth_headers(owner)).status_code == 200
        assert _count(db_session, Listing) == 0 and _count(db_session, Removal) == 2


class TestDeactivatedLogin:
    def test_a_deactivated_member_cannot_log_in(self, client, db_session):
        """TC-API-REM-042 | AC-03.3 | T06 | negative | a deactivated account is told so at login; a wrong password still only says invalid"""
        user = make_user(db_session, is_active=False)
        right = client.post("/api/auth/login", json={"email": user.email, "password": "Passw0rd1"})
        wrong = client.post("/api/auth/login", json={"email": user.email, "password": "Wrong0000"})
        assert right.status_code == 403 and "deactivated" in right.json()["detail"].lower()
        assert wrong.status_code == 401 and "access_token" not in right.json()
