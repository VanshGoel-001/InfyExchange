"""API tests: admin moderation and audit trail (tasks T12, T13).

test_authorization.py already covers: non-admin blocked from /stats, admin routes need a token,
admin can read /stats. These add per-endpoint behaviour and the audit rules.
"""

import json

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Interest, Listing, Need, User
from app.services import rate_limit
from app.utils.enums import InterestStatus, ListingStatus, NeedStatus
from tests.conftest import auth_headers, make_user
from tests.support import add_image, add_interest, add_listing, add_need

ADMIN = "/api/admin"


@pytest.fixture()
def admin(db_session):
    return make_user(db_session, is_admin=True)


def _audit(db):
    db.expire_all()
    return db.scalars(select(AuditLog).order_by(AuditLog.id)).all()


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


class TestAdminAccessControl:
    ENDPOINTS = [
        ("GET", "/stats", None),
        ("GET", "/users", None),
        ("PATCH", "/users/1", {"is_active": False}),
        ("GET", "/listings", None),
        ("PATCH", "/listings/1/status?status=SOLD", None),
        ("DELETE", "/listings/1", None),
        ("GET", "/needs", None),
        ("DELETE", "/needs/1", None),
        ("GET", "/audit-logs", None),
    ]

    @pytest.mark.parametrize("method, path, body", ENDPOINTS)
    def test_non_admin_is_forbidden_everywhere(self, client, db_session, method, path, body):
        """TC-API-ADM-001 | AC-12.1 | T12 | negative | every admin route returns 403 for a regular member"""
        member = make_user(db_session)
        response = client.request(method, ADMIN + path, json=body, headers=auth_headers(member))
        assert response.status_code == 403

    @pytest.mark.parametrize("method, path, body", ENDPOINTS)
    def test_anonymous_is_rejected_everywhere(self, client, method, path, body):
        """TC-API-ADM-002 | AC-12.1 | T12 | negative | every admin route rejects callers without a token"""
        response = client.request(method, ADMIN + path, json=body)
        assert response.status_code in (401, 403)

    def test_admin_requests_are_throttled(self, client, admin, monkeypatch):
        """TC-API-ADM-003 | AC-12.7 | T12, T13 | boundary | with the admin limit at 2 the third request is 429"""
        monkeypatch.setattr(rate_limit.admin_limiter, "max_requests", 2)
        headers = auth_headers(admin)
        assert [client.get(f"{ADMIN}/stats", headers=headers).status_code for _ in range(2)] == [200, 200]
        assert client.get(f"{ADMIN}/stats", headers=headers).status_code == 429

    def test_deactivated_admin_loses_access(self, client, db_session):
        """TC-API-ADM-004 | AC-12.1, AC-03.3 | T12, T06 | negative | an admin whose account is deactivated gets 403"""
        inactive_admin = make_user(db_session, is_admin=True, is_active=False)
        assert client.get(f"{ADMIN}/stats", headers=auth_headers(inactive_admin)).status_code == 403


class TestAdminStats:
    def test_counters_match_data(self, client, db_session, admin):
        """TC-API-ADM-010 | AC-12.2 | T12 | positive | total/active counts for users, listings, needs and interests"""
        member, inactive = make_user(db_session), make_user(db_session, is_active=False)
        active_listing = add_listing(db_session, member)
        sold_listing = add_listing(db_session, member, status=ListingStatus.SOLD)
        add_need(db_session, member)
        add_need(db_session, member, status=NeedStatus.CLOSED)
        add_interest(db_session, active_listing, inactive, InterestStatus.ACCEPTED)
        add_interest(db_session, sold_listing, inactive, InterestStatus.PENDING)
        body = client.get(f"{ADMIN}/stats", headers=auth_headers(admin)).json()
        assert body == {
            "total_users": 3, "active_users": 2,
            "total_listings": 2, "active_listings": 1,
            "total_needs": 2, "active_needs": 1,
            "total_interests": 2, "accepted_interests": 1,
        }

    def test_empty_platform_reports_only_the_admin(self, client, admin):
        """TC-API-ADM-011 | AC-12.2 | T12 | boundary | with no content, everything but the admin user is zero"""
        body = client.get(f"{ADMIN}/stats", headers=auth_headers(admin)).json()
        assert body["total_users"] == 1 and body["active_users"] == 1
        assert body["total_listings"] == body["total_needs"] == body["total_interests"] == 0


class TestAdminUsers:
    def test_list_returns_total_items_and_no_secrets(self, client, db_session, admin):
        """TC-API-ADM-020 | AC-12.3 | T12 | positive | {total, items[]} with profile fields and without password data"""
        make_user(db_session)
        body = client.get(f"{ADMIN}/users", headers=auth_headers(admin)).json()
        assert body["total"] == 2
        assert len(body["items"]) == 2
        for item in body["items"]:
            assert {"id", "name", "email", "phone", "role", "is_admin", "is_active"} <= set(item)
            assert "password_hash" not in item

    def test_search_matches_email_and_name_case_insensitively(self, client, db_session, admin):
        """TC-API-ADM-021 | AC-12.3 | T12 | positive | search finds substrings of email or name; no match gives total 0"""
        make_user(db_session, email="findme@gmail.com")
        named = make_user(db_session)
        named.name = "Zed Special"
        db_session.commit()
        headers = auth_headers(admin)
        assert client.get(f"{ADMIN}/users", params={"search": "FINDME"}, headers=headers).json()["total"] == 1
        assert client.get(f"{ADMIN}/users", params={"search": "zed spec"}, headers=headers).json()["total"] == 1
        assert client.get(f"{ADMIN}/users", params={"search": "nobody-matches"}, headers=headers).json() == {"total": 0, "items": []}

    def test_pagination_keeps_full_total(self, client, db_session, admin):
        """TC-API-ADM-022 | AC-12.3 | T12 | boundary | limit reduces items but total still counts every match"""
        for _ in range(2):
            make_user(db_session)
        body = client.get(f"{ADMIN}/users", params={"limit": 2}, headers=auth_headers(admin)).json()
        assert body["total"] == 3 and len(body["items"]) == 2

    @pytest.mark.parametrize("limit, expected", [(0, 422), (1, 200), (200, 200), (201, 422)])
    def test_limit_boundaries(self, client, admin, limit, expected):
        """TC-API-ADM-023 | AC-12.3 | T12 | boundary | admin user lists accept limit 1-200"""
        assert client.get(f"{ADMIN}/users", params={"limit": limit}, headers=auth_headers(admin)).status_code == expected

    def test_deactivate_user_updates_flag_and_writes_audit(self, client, db_session, admin):
        """TC-API-ADM-024 | AC-12.4, AC-13.1 | T12 | positive | is_active=false persists and an UPDATE_USER audit row records from/to"""
        target = make_user(db_session)
        response = client.patch(f"{ADMIN}/users/{target.id}", json={"is_active": False}, headers=auth_headers(admin))
        assert response.status_code == 200
        db_session.expire_all()
        assert db_session.get(User, target.id).is_active is False
        (entry,) = _audit(db_session)
        assert (entry.action, entry.target_type, entry.target_id, entry.actor_id) == ("UPDATE_USER", "USER", str(target.id), admin.id)
        assert entry.ip_address
        details = json.loads(entry.details)
        assert details["email"] == target.email
        assert details["changes"]["is_active"] == {"from": True, "to": False}

    def test_deactivation_takes_effect_immediately(self, client, db_session, admin):
        """TC-API-ADM-025 | AC-12.4, AC-03.3 | T12, T06 | business | the deactivated member's existing token is refused on the next call"""
        target = make_user(db_session)
        headers = auth_headers(target)
        assert client.get("/api/users/me", headers=headers).status_code == 200
        client.patch(f"{ADMIN}/users/{target.id}", json={"is_active": False}, headers=auth_headers(admin))
        assert client.get("/api/users/me", headers=headers).status_code == 403

    def test_reactivation_restores_access(self, client, db_session, admin):
        """TC-API-ADM-026 | AC-12.4 | T12 | business | setting is_active back to true lets the member in again"""
        target = make_user(db_session, is_active=False)
        client.patch(f"{ADMIN}/users/{target.id}", json={"is_active": True}, headers=auth_headers(admin))
        assert client.get("/api/users/me", headers=auth_headers(target)).status_code == 200

    def test_grant_admin_rights(self, client, db_session, admin):
        """TC-API-ADM-027 | AC-12.4 | T12 | positive | promoting a member lets them reach admin routes"""
        target = make_user(db_session)
        assert client.get(f"{ADMIN}/stats", headers=auth_headers(target)).status_code == 403
        client.patch(f"{ADMIN}/users/{target.id}", json={"is_admin": True}, headers=auth_headers(admin))
        assert client.get(f"{ADMIN}/stats", headers=auth_headers(target)).status_code == 200

    def test_admin_can_revoke_another_admin(self, client, db_session, admin):
        """TC-API-ADM-028 | AC-12.4 | T12 | positive | demoting a different admin succeeds"""
        other = make_user(db_session, is_admin=True)
        response = client.patch(f"{ADMIN}/users/{other.id}", json={"is_admin": False}, headers=auth_headers(admin))
        assert response.status_code == 200
        assert client.get(f"{ADMIN}/stats", headers=auth_headers(other)).status_code == 403

    def test_admin_cannot_revoke_own_rights(self, client, db_session, admin):
        """TC-API-ADM-029 | AC-12.4 | T12 | negative | self-demotion gives 400, keeps admin rights and writes no audit row"""
        response = client.patch(f"{ADMIN}/users/{admin.id}", json={"is_admin": False}, headers=auth_headers(admin))
        assert response.status_code == 400
        assert response.json()["detail"] == "Cannot revoke your own admin rights."
        db_session.expire_all()
        assert db_session.get(User, admin.id).is_admin is True
        assert _audit(db_session) == []

    def test_unknown_user_is_404(self, client, admin):
        """TC-API-ADM-030 | AC-12.4 | T12 | negative | updating a missing user gives 404"""
        response = client.patch(f"{ADMIN}/users/999999", json={"is_active": False}, headers=auth_headers(admin))
        assert response.status_code == 404

    @pytest.mark.parametrize("body", [{}, {"is_active": True}, {"is_admin": False}], ids=["empty", "same-active", "same-admin"])
    def test_no_op_updates_write_no_audit(self, client, db_session, admin, body):
        """TC-API-ADM-031 | AC-13.2 | T12 | boundary | empty or unchanged payloads succeed without creating an audit row"""
        target = make_user(db_session)
        response = client.patch(f"{ADMIN}/users/{target.id}", json=body, headers=auth_headers(admin))
        assert response.status_code == 200
        assert _audit(db_session) == []

    def test_non_boolean_flag_is_422(self, client, db_session, admin):
        """TC-API-ADM-032 | AC-12.4 | T12 | negative | a non-boolean value is rejected"""
        target = make_user(db_session)
        response = client.patch(f"{ADMIN}/users/{target.id}", json={"is_active": "maybe"}, headers=auth_headers(admin))
        assert response.status_code == 422


class TestAdminListings:
    def test_list_has_owner_contact_for_moderation_and_image_count(self, client, db_session, admin):
        """TC-API-ADM-040 | AC-12.5 | T12 | positive | admin list includes owner name/email and image_count"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner)
        add_image(db_session, listing)
        add_image(db_session, listing)
        body = client.get(f"{ADMIN}/listings", headers=auth_headers(admin)).json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["owner_email"] == owner.email
        assert item["owner_name"] == owner.name
        assert item["image_count"] == 2

    def test_status_filter_and_search(self, client, db_session, admin):
        """TC-API-ADM-041 | AC-12.5 | T12 | positive | status_filter and title search narrow the list; all statuses are visible by default"""
        owner = make_user(db_session)
        add_listing(db_session, owner, title="Racket A")
        add_listing(db_session, owner, title="Racket B", status=ListingStatus.SOLD)
        add_listing(db_session, owner, title="Ball")
        headers = auth_headers(admin)
        assert client.get(f"{ADMIN}/listings", headers=headers).json()["total"] == 3
        sold = client.get(f"{ADMIN}/listings", params={"status_filter": "SOLD"}, headers=headers).json()
        assert [i["title"] for i in sold["items"]] == ["Racket B"]
        assert client.get(f"{ADMIN}/listings", params={"search": "racket"}, headers=headers).json()["total"] == 2

    @pytest.mark.parametrize("params, expected", [({"status_filter": "GONE"}, 422), ({"limit": 0}, 422), ({"limit": 201}, 422), ({"limit": 200}, 200)])
    def test_list_parameter_boundaries(self, client, admin, params, expected):
        """TC-API-ADM-042 | AC-12.5 | T12 | boundary | invalid status and limits outside 1-200 are rejected"""
        assert client.get(f"{ADMIN}/listings", params=params, headers=auth_headers(admin)).status_code == expected

    def test_status_change_updates_listing_hides_it_and_audits(self, client, db_session, admin):
        """TC-API-ADM-043 | AC-12.5, AC-13.1 | T12 | positive | status=UNAVAILABLE persists, removes the listing from public browse, and audits old/new"""
        listing = add_listing(db_session, make_user(db_session))
        response = client.patch(f"{ADMIN}/listings/{listing.id}/status", params={"status": "UNAVAILABLE"}, headers=auth_headers(admin))
        assert response.status_code == 200
        db_session.expire_all()
        assert db_session.get(Listing, listing.id).status == ListingStatus.UNAVAILABLE
        assert client.get("/api/listings").json() == []
        (entry,) = _audit(db_session)
        assert (entry.action, entry.target_type, entry.target_id) == ("UPDATE_LISTING_STATUS", "LISTING", str(listing.id))
        details = json.loads(entry.details)
        assert (details["old_status"], details["new_status"]) == ("ACTIVE", "UNAVAILABLE")

    @pytest.mark.parametrize("params, expected", [({"status": "GONE"}, 422), ({}, 422)], ids=["bad-status", "missing-status"])
    def test_status_change_requires_valid_status(self, client, db_session, admin, params, expected):
        """TC-API-ADM-044 | AC-12.5 | T12 | negative | missing or unknown status query value is 422 and nothing changes"""
        listing = add_listing(db_session, make_user(db_session))
        response = client.patch(f"{ADMIN}/listings/{listing.id}/status", params=params, headers=auth_headers(admin))
        assert response.status_code == expected
        assert _audit(db_session) == []

    def test_status_change_unknown_listing_is_404(self, client, admin):
        """TC-API-ADM-045 | AC-12.5 | T12 | negative | missing listing gives 404"""
        response = client.patch(f"{ADMIN}/listings/999999/status", params={"status": "SOLD"}, headers=auth_headers(admin))
        assert response.status_code == 404

    def test_delete_removes_listing_and_interests_and_audits(self, client, db_session, admin):
        """TC-API-ADM-046 | AC-12.5, AC-13.1, AC-19.3 | T12 | positive | deleting a listing removes it and its interests; DELETE_LISTING audit stores the title"""
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner, title="Remove me")
        add_interest(db_session, listing, buyer)
        response = client.delete(f"{ADMIN}/listings/{listing.id}", headers=auth_headers(admin))
        assert response.status_code == 200
        db_session.expire_all()
        assert _count(db_session, Listing) == 0
        assert _count(db_session, Interest) == 0
        (entry,) = _audit(db_session)
        assert entry.action == "DELETE_LISTING"
        assert json.loads(entry.details) == {"title": "Remove me"}

    def test_delete_unknown_listing_is_404(self, client, admin):
        """TC-API-ADM-047 | AC-12.5 | T12 | negative | missing listing gives 404"""
        assert client.delete(f"{ADMIN}/listings/999999", headers=auth_headers(admin)).status_code == 404


class TestAdminNeeds:
    def test_list_filter_and_search(self, client, db_session, admin):
        """TC-API-ADM-050 | AC-12.6 | T12 | positive | admin sees every need with poster email; status_filter and search narrow it"""
        user = make_user(db_session)
        add_need(db_session, user, title="Cricket bat")
        add_need(db_session, user, title="Squash racket", status=NeedStatus.FULFILLED)
        headers = auth_headers(admin)
        body = client.get(f"{ADMIN}/needs", headers=headers).json()
        assert body["total"] == 2
        assert body["items"][0]["user_email"] == user.email
        assert client.get(f"{ADMIN}/needs", params={"status_filter": "FULFILLED"}, headers=headers).json()["total"] == 1
        assert client.get(f"{ADMIN}/needs", params={"search": "CRICKET"}, headers=headers).json()["total"] == 1

    @pytest.mark.parametrize("params, expected", [({"status_filter": "GONE"}, 422), ({"limit": 201}, 422), ({"limit": 1}, 200)])
    def test_list_parameter_boundaries(self, client, admin, params, expected):
        """TC-API-ADM-051 | AC-12.6 | T12 | boundary | invalid status and limit > 200 are rejected"""
        assert client.get(f"{ADMIN}/needs", params=params, headers=auth_headers(admin)).status_code == expected

    def test_delete_removes_need_and_audits(self, client, db_session, admin):
        """TC-API-ADM-052 | AC-12.6, AC-13.1 | T12 | positive | deleting a need removes it and writes DELETE_NEED with its title"""
        need_id = add_need(db_session, make_user(db_session), title="Take down").id
        assert client.delete(f"{ADMIN}/needs/{need_id}", headers=auth_headers(admin)).status_code == 200
        assert _count(db_session, Need) == 0
        (entry,) = _audit(db_session)
        assert (entry.action, entry.target_type, entry.target_id) == ("DELETE_NEED", "NEED", str(need_id))
        assert json.loads(entry.details) == {"title": "Take down"}

    def test_delete_unknown_need_is_404(self, client, admin):
        """TC-API-ADM-053 | AC-12.6 | T12 | negative | missing need gives 404"""
        assert client.delete(f"{ADMIN}/needs/999999", headers=auth_headers(admin)).status_code == 404


class TestAuditLog:
    def test_log_is_newest_first_with_actor_name(self, client, db_session, admin):
        """TC-API-ADM-060 | AC-13.3 | T12 | business | entries are returned newest first and show the actor's name"""
        listing = add_listing(db_session, make_user(db_session))
        need = add_need(db_session, make_user(db_session))
        headers = auth_headers(admin)
        client.delete(f"{ADMIN}/needs/{need.id}", headers=headers)
        client.patch(f"{ADMIN}/listings/{listing.id}/status", params={"status": "SOLD"}, headers=headers)
        body = client.get(f"{ADMIN}/audit-logs", headers=headers).json()
        assert body["total"] == 2
        assert [i["action"] for i in body["items"]] == ["UPDATE_LISTING_STATUS", "DELETE_NEED"]
        assert all(i["actor_name"] == admin.name for i in body["items"])

    def test_empty_log(self, client, admin):
        """TC-API-ADM-061 | AC-13.3 | T12 | boundary | with no admin actions the log is empty"""
        assert client.get(f"{ADMIN}/audit-logs", headers=auth_headers(admin)).json() == {"total": 0, "items": []}

    @pytest.mark.parametrize("limit, expected", [(0, 422), (1, 200), (100, 200), (101, 422)])
    def test_limit_boundaries(self, client, admin, limit, expected):
        """TC-API-ADM-062 | AC-13.3 | T12 | boundary | audit log limit accepts 1-100 only"""
        assert client.get(f"{ADMIN}/audit-logs", params={"limit": limit}, headers=auth_headers(admin)).status_code == expected

    def test_pagination_keeps_full_total(self, client, db_session, admin):
        """TC-API-ADM-063 | AC-13.3 | T12 | boundary | limit/skip page the log while total counts all entries"""
        headers = auth_headers(admin)
        for _ in range(3):
            need = add_need(db_session, make_user(db_session))
            client.delete(f"{ADMIN}/needs/{need.id}", headers=headers)
        page = client.get(f"{ADMIN}/audit-logs", params={"limit": 2, "skip": 2}, headers=headers).json()
        assert page["total"] == 3 and len(page["items"]) == 1
