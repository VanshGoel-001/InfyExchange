"""API tests: the notification bell (/api/notifications).

TC ids are new; AC/T columns reuse the nearest derived criteria because no approved spec exists
for this feature yet (see test.md).
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Notification
from app.services import rate_limit
from tests.conftest import auth_headers, make_user

URL = "/api/notifications"


def _add(db, user, message="hello", read=False, minutes_ago=0, kind="enquiry_received", interest_id=None):
    row = Notification(
        user_id=user.id, kind=kind, message=message, interest_id=interest_id,
        created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
        read_at=datetime.utcnow() if read else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_requires_a_token(client):
    """TC-API-NOT-001 | AC-02.1 | T13 | negative | every notification route rejects an anonymous caller"""
    for method, path in (("get", URL), ("post", f"{URL}/read-all"), ("post", f"{URL}/1/read")):
        assert getattr(client, method)(path).status_code in (401, 403)


def test_list_is_newest_first_with_the_unread_total(client, db_session):
    """TC-API-NOT-002 | AC-09.1 | T10 | positive | items come newest first with a read flag, plus the count the bell badge shows"""
    me = make_user(db_session)
    old = _add(db_session, me, "old", read=True, minutes_ago=30)
    mid = _add(db_session, me, "mid", minutes_ago=20, interest_id=7)
    new = _add(db_session, me, "new", minutes_ago=10)
    body = client.get(URL, headers=auth_headers(me)).json()
    assert body["unread_count"] == 2
    assert [(i["id"], i["read"]) for i in body["items"]] == [(new.id, False), (mid.id, False), (old.id, True)]
    assert set(body["items"][0]) == {"id", "kind", "message", "interest_id", "created_at", "read"}
    assert body["items"][1]["interest_id"] == 7


def test_the_list_only_ever_holds_my_own_notifications(client, db_session):
    """TC-API-NOT-003 | AC-10.1 | T13 | negative | I never see, count or change anyone else's notifications"""
    me, other = make_user(db_session), make_user(db_session)
    _add(db_session, other, "secret")
    body = client.get(URL, headers=auth_headers(me)).json()
    assert body == {"unread_count": 0, "items": []}


def test_unread_count_covers_everything_not_just_the_page(client, db_session):
    """TC-API-NOT-004 | AC-09.1 | T10 | boundary | with limit=2 only two items come back but unread_count still counts all unread ones"""
    me = make_user(db_session)
    for n in range(5):
        _add(db_session, me, f"n{n}", minutes_ago=n)
    body = client.get(URL, params={"limit": 2}, headers=auth_headers(me)).json()
    assert len(body["items"]) == 2 and body["unread_count"] == 5


@pytest.mark.parametrize("limit, expected", [(0, 422), (1, 200), (50, 200), (51, 422)])
def test_limit_boundaries(client, db_session, limit, expected):
    """TC-API-NOT-005 | AC-18.1 | T16 | boundary | limit must be 1 to 50"""
    me = make_user(db_session)
    assert client.get(URL, params={"limit": limit}, headers=auth_headers(me)).status_code == expected


def test_mark_one_read(client, db_session):
    """TC-API-NOT-006 | AC-09.1 | T10 | positive | marking one notification read lowers the count by one and leaves the others unread"""
    me = make_user(db_session)
    first, second = _add(db_session, me, "a"), _add(db_session, me, "b")
    assert client.post(f"{URL}/{first.id}/read", headers=auth_headers(me)).json() == {"read": True}
    assert client.post(f"{URL}/{first.id}/read", headers=auth_headers(me)).status_code == 200  # repeating is harmless
    body = client.get(URL, headers=auth_headers(me)).json()
    assert body["unread_count"] == 1
    assert {i["id"]: i["read"] for i in body["items"]} == {first.id: True, second.id: False}


def test_cannot_mark_someone_elses_notification(client, db_session):
    """TC-API-NOT-007 | AC-10.1 | T13 | negative | another user's notification is 404 (not 403, so ids cannot be probed) and stays unread; an unknown id is 404"""
    me, other = make_user(db_session), make_user(db_session)
    theirs = _add(db_session, other, "theirs")
    assert client.post(f"{URL}/{theirs.id}/read", headers=auth_headers(me)).status_code == 404
    assert client.post(f"{URL}/999999/read", headers=auth_headers(me)).status_code == 404
    db_session.refresh(theirs)
    assert theirs.read_at is None


def test_read_all_marks_only_mine(client, db_session):
    """TC-API-NOT-008 | AC-09.1 | T10 | positive | 'mark all read' clears my badge and does not touch another user's unread notifications"""
    me, other = make_user(db_session), make_user(db_session)
    for n in range(3):
        _add(db_session, me, f"m{n}")
    theirs = _add(db_session, other, "theirs")
    assert client.post(f"{URL}/read-all", headers=auth_headers(me)).json() == {"unread_count": 0}
    assert client.get(URL, headers=auth_headers(me)).json()["unread_count"] == 0
    db_session.refresh(theirs)
    assert theirs.read_at is None


def test_read_stamps_are_kept(client, db_session):
    """TC-API-NOT-009 | AC-09.1 | T10 | business | read-all does not overwrite the time an earlier notification was read"""
    me = make_user(db_session)
    row = _add(db_session, me, "already read", read=True)
    stamped = row.read_at
    client.post(f"{URL}/read-all", headers=auth_headers(me))
    db_session.refresh(row)
    assert row.read_at == stamped


def test_polling_and_marking_are_rate_limited_per_user(client, db_session, monkeypatch):
    """TC-API-NOT-010 | AC-09.1 | T13 | boundary | with the limits at 1 the second poll and the second mark-read are 429 for that user only"""
    monkeypatch.setattr(rate_limit.poll_limiter, "max_requests", 1)
    monkeypatch.setattr(rate_limit.action_limiter, "max_requests", 1)
    me, other = make_user(db_session), make_user(db_session)
    assert client.get(URL, headers=auth_headers(me)).status_code == 200
    assert client.get(URL, headers=auth_headers(me)).status_code == 429
    assert client.get(URL, headers=auth_headers(other)).status_code == 200
    assert client.post(f"{URL}/read-all", headers=auth_headers(me)).status_code == 200
    assert client.post(f"{URL}/read-all", headers=auth_headers(me)).status_code == 429


def test_responses_are_not_cached(client, db_session):
    """TC-API-NOT-011 | AC-04.1 | T13 | business | notification responses carry Cache-Control: no-store"""
    me = make_user(db_session)
    assert client.get(URL, headers=auth_headers(me)).headers["cache-control"] == "no-store"
