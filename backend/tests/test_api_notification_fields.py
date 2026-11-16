"""API tests: notifications carry structured fields (kind, actor, listing, detail), not a stored sentence.

The SPA words each notification from these fields. The old `message` column is still written for the
previous release but is never sent by the API.
"""

from datetime import datetime

from sqlalchemy import select

from app.models import Notification
from app.services.notify import notify
from tests.conftest import auth_headers, make_user
from tests.support import add_interest, add_listing

URL = "/api/notifications"
INTERESTS = "/api/interests"


def _mine(client, user):
    return client.get(URL, headers=auth_headers(user)).json()["items"]


def _rows(db, user):
    return db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.id)).all()


def test_response_has_structured_fields_and_no_sentence(client, db_session):
    """TC-API-NOT-020 | AC-09.1 | T10 | positive | each item has kind, actor_name, listing, detail, interest and read flag, and never the stored message"""
    me, other = make_user(db_session), make_user(db_session)
    other.name = "Ravi Kumar"
    db_session.add(Notification(
        user_id=me.id, kind="enquiry_received", message="stored sentence <b>hi</b> http://example.com",
        actor_id=other.id, listing_title="Racket", created_at=datetime.utcnow(),
    ))
    db_session.commit()
    item = _mine(client, me)[0]
    assert set(item) == {"id", "kind", "actor_name", "listing_id", "listing_title", "detail", "interest_id", "created_at", "read"}
    assert (item["kind"], item["actor_name"], item["listing_title"]) == ("enquiry_received", "Ravi Kumar", "Racket")
    assert "stored sentence" not in str(item)


def test_enquiry_notifies_the_owner_with_who_and_what(client, db_session):
    """TC-API-NOT-021 | AC-09.1 | T10 | business | sending an enquiry stores the enquirer as actor and the listing title for the owner"""
    owner, buyer = make_user(db_session), make_user(db_session)
    listing = add_listing(db_session, owner, title="Yonex racket")
    response = client.post(f"{INTERESTS}/listing/{listing.id}", json={"message": "hi"}, headers=auth_headers(buyer))
    assert response.status_code == 201
    row = _rows(db_session, owner)[0]
    assert (row.kind, row.actor_id, row.listing_title) == ("enquiry_received", buyer.id, "Yonex racket")
    assert _mine(client, owner)[0]["actor_name"] == buyer.name


def test_accept_notifies_the_buyer_with_the_owner_as_actor(client, db_session):
    """TC-API-NOT-022 | AC-09.3 | T10 | business | accepting stores the owner as actor and links the notification to the enquiry"""
    owner, buyer = make_user(db_session), make_user(db_session)
    interest = add_interest(db_session, add_listing(db_session, owner, title="Bat"), buyer)
    client.patch(f"{INTERESTS}/{interest.id}/accept", headers=auth_headers(owner))
    row = _rows(db_session, buyer)[0]
    assert (row.kind, row.actor_id, row.listing_title, row.interest_id) == ("enquiry_accepted", owner.id, "Bat", interest.id)


def test_chat_message_keeps_a_short_plain_preview(client, db_session):
    """TC-API-NOT-023 | AC-10.1 | T10 | business | the first unread chat message stores a clipped preview as plain text, and the sender is the actor"""
    owner, buyer = make_user(db_session), make_user(db_session)
    interest = add_interest(db_session, add_listing(db_session, owner), buyer)
    client.patch(f"{INTERESTS}/{interest.id}/accept", headers=auth_headers(owner))
    body = '<script>alert(1)</script> https://example.com/' + "x" * 200
    client.post(f"{INTERESTS}/{interest.id}/messages", json={"body": body}, headers=auth_headers(buyer))
    row = [r for r in _rows(db_session, owner) if r.kind == "new_message"][0]
    assert row.actor_id == buyer.id
    assert len(row.detail) <= 80 and row.detail.startswith("<script>")


def test_nobody_is_notified_about_their_own_action(db_session):
    """TC-API-NOT-024 | AC-09.1 | T10 | business | notify() skips a notification whose actor is the recipient, and keeps one from someone else"""
    me, other = make_user(db_session), make_user(db_session)
    notify(db_session, me.id, "enquiry_received", "x", actor_id=me.id)
    notify(db_session, me.id, "enquiry_received", "x", actor_id=other.id)
    db_session.commit()
    assert [r.actor_id for r in _rows(db_session, me)] == [other.id]


def test_old_rows_without_an_actor_still_show_who_it_was(client, db_session):
    """TC-API-NOT-025 | AC-09.1 | T10 | business | a notification written before the structured columns shows the owner/buyer taken from its enquiry"""
    owner, buyer = make_user(db_session), make_user(db_session)
    interest = add_interest(db_session, add_listing(db_session, owner, title="Old title"), buyer)
    now = datetime.utcnow()
    db_session.add_all([
        Notification(user_id=buyer.id, kind="enquiry_accepted", message="old", interest_id=interest.id, created_at=now),
        Notification(user_id=owner.id, kind="enquiry_received", message="old", interest_id=interest.id, created_at=now),
        Notification(user_id=owner.id, kind="new_message", message="old", interest_id=interest.id, created_at=now),
    ])
    db_session.commit()
    by_buyer = _mine(client, buyer)[0]
    assert (by_buyer["actor_name"], by_buyer["listing_title"], by_buyer["listing_id"]) == (owner.name, "Old title", interest.listing_id)
    assert {i["kind"]: i["actor_name"] for i in _mine(client, owner)} == {"enquiry_received": buyer.name, "new_message": buyer.name}


def test_names_and_titles_are_clipped_in_the_response(client, db_session):
    """TC-API-NOT-026 | AC-09.1 | T10 | boundary | a very long name or title cannot widen the panel: the API clips them"""
    me, other = make_user(db_session), make_user(db_session)
    other.name = "N" * 100
    db_session.add(Notification(
        user_id=me.id, kind="enquiry_received", message="m", actor_id=other.id,
        listing_title="T" * 150, created_at=datetime.utcnow(),
    ))
    db_session.commit()
    item = _mine(client, me)[0]
    assert len(item["actor_name"]) <= 40 and len(item["listing_title"]) <= 150


def test_notification_whose_sender_is_gone_is_hidden(client, db_session):
    """TC-API-NOT-027 | AC-09.1 | T10 | boundary | a listing-removed notice with no actor and no enquiry to find one in is hidden, not shown with a made-up name"""
    me = make_user(db_session)
    db_session.add(Notification(user_id=me.id, kind="listing_removed", message="m", listing_title="Gone", created_at=datetime.utcnow()))
    db_session.commit()
    assert _mine(client, me) == []
