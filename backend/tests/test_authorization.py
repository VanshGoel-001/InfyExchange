"""AUTHZ-001..004: backend-enforced authorization and object ownership."""

from tests.conftest import (
    auth_headers,
    make_interest,
    make_listing,
    make_user,
)

from app.utils.enums import InterestStatus


def test_cannot_read_other_users_profile_endpoint(client, db_session):
    owner = make_user(db_session)
    attacker = make_user(db_session)

    # /api/users/me always resolves the caller from the token, never from input
    response = client.get(
        "/api/users/me",
        headers=auth_headers(attacker),
    )

    assert response.status_code == 200
    assert response.json()["id"] == attacker.id
    assert response.json()["id"] != owner.id


def test_horizontal_escalation_listing_update_blocked(client, db_session):
    owner = make_user(db_session)
    attacker = make_user(db_session)
    listing = make_listing(db_session, owner)

    response = client.put(
        f"/api/listings/{listing.id}",
        json={"title": "Hijacked title"},
        headers=auth_headers(attacker),
    )

    assert response.status_code == 403


def test_horizontal_escalation_listing_delete_blocked(client, db_session):
    owner = make_user(db_session)
    attacker = make_user(db_session)
    listing = make_listing(db_session, owner)

    response = client.delete(
        f"/api/listings/{listing.id}",
        headers=auth_headers(attacker),
    )

    assert response.status_code == 403


def test_owner_can_update_own_listing(client, db_session):
    owner = make_user(db_session)
    listing = make_listing(db_session, owner)

    response = client.put(
        f"/api/listings/{listing.id}",
        json={"title": "Legitimate update"},
        headers=auth_headers(owner),
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Legitimate update"


def test_vertical_escalation_admin_stats_blocked(client, db_session):
    normal_user = make_user(db_session)

    response = client.get(
        "/api/admin/stats",
        headers=auth_headers(normal_user),
    )

    assert response.status_code == 403


def test_admin_endpoints_require_authentication(client):
    response = client.get("/api/admin/stats")

    assert response.status_code in (401, 403)


def test_admin_can_access_admin_stats(client, db_session):
    admin = make_user(db_session, is_admin=True)

    response = client.get(
        "/api/admin/stats",
        headers=auth_headers(admin),
    )

    assert response.status_code == 200


def test_cannot_show_interest_in_own_listing(client, db_session):
    owner = make_user(db_session)
    listing = make_listing(db_session, owner)

    response = client.post(
        f"/api/interests/listing/{listing.id}",
        json={"message": "talking to myself"},
        headers=auth_headers(owner),
    )

    assert response.status_code == 400


def test_contact_details_blocked_before_acceptance(client, db_session):
    owner = make_user(db_session)
    interested = make_user(db_session)
    listing = make_listing(db_session, owner)
    interest = make_interest(
        db_session,
        listing,
        interested,
        InterestStatus.PENDING,
    )

    response = client.get(
        f"/api/interests/{interest.id}/contact",
        headers=auth_headers(interested),
    )

    assert response.status_code == 403


def test_contact_details_blocked_for_third_party(client, db_session):
    owner = make_user(db_session)
    interested = make_user(db_session)
    outsider = make_user(db_session)
    listing = make_listing(db_session, owner)
    interest = make_interest(
        db_session,
        listing,
        interested,
        InterestStatus.ACCEPTED,
    )

    response = client.get(
        f"/api/interests/{interest.id}/contact",
        headers=auth_headers(outsider),
    )

    assert response.status_code == 403


def test_contact_details_visible_to_participants(client, db_session):
    owner = make_user(db_session)
    interested = make_user(db_session)
    listing = make_listing(db_session, owner)
    interest = make_interest(
        db_session,
        listing,
        interested,
        InterestStatus.ACCEPTED,
    )

    for participant, expected_email in (
        (owner, interested.email),
        (interested, owner.email),
    ):
        response = client.get(
            f"/api/interests/{interest.id}/contact",
            headers=auth_headers(participant),
        )

        assert response.status_code == 200
        assert response.json()["email"] == expected_email
