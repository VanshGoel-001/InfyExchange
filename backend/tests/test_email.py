"""Email: templates, the two adapters, the registration and enquiry emails, and the admin retry flow.

The Brevo adapter is exercised against a real HTTP server on localhost (the ``brevo`` fixture in
conftest.py): the application builds and POSTs the request for real, and the tests read what
arrived. That verifies the request we send, not Brevo's behaviour, which needs a live API key.

TC ids are new; AC/T columns reuse the nearest derived criteria (AC-01 registration, AC-09
interests, AC-13 admin) because no approved spec exists for this feature yet (see test.md).
"""

import asyncio
import logging
from datetime import datetime, timedelta

import pytest
from jinja2.exceptions import UndefinedError
from sqlalchemy import select

from app.config import settings
from app.models import AuditLog, FailedEmail, User
from app.services import email_service
from app.services.cleanup import cleanup_expired_data
from app.services.email_service import (
    BrevoEmailAdapter,
    ConsoleEmailAdapter,
    EmailDeliveryError,
    EmailMessage,
    _templates,
    get_adapter,
)
from tests.conftest import auth_headers, make_user, register_payload
from tests.support import add_listing

REGISTER = "/api/auth/register"
ENQUIRE = "/api/interests/listing"
ADMIN = "/api/admin/failed-emails"


def _render(template, **context):
    return _templates.get_template(template).render(**context)


def _message(**overrides):
    fields = dict(to_email="ann@gmail.com", to_name="Ann", subject="Hello", html="<p>Hi</p>")
    fields.update(overrides)
    return EmailMessage(**fields)


def _add_failed(db, **overrides) -> FailedEmail:
    now = datetime.utcnow()
    fields = dict(
        to_email="ann@gmail.com", to_name="Ann", subject="Welcome to InfyExchange", html="<p>Hi Ann</p>",
        error="EmailDeliveryError: Brevo rejected the email (HTTP 500, code=None)",
        attempts=1, created_at=now, last_attempt_at=now,
    )
    fields.update(overrides)
    row = FailedEmail(**fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestTemplates:
    def test_welcome_greets_by_name(self):
        """TC-EML-TPL-001 | AC-01.1 | T05 | positive | the welcome email names the new user"""
        assert "Hi Ann," in _render("welcome.html", name="Ann")

    def test_user_text_is_escaped_not_rendered_as_markup(self):
        """TC-EML-TPL-002 | AC-18.2 | T16 | negative | a name or message containing HTML comes out escaped, so it cannot inject markup or links"""
        hostile = '<script>alert(1)</script><a href="https://evil.test">x</a>'
        for html in (
            _render("welcome.html", name=hostile),
            _render("enquiry_admin.html", listing_title=hostile, owner_name=hostile, sender_name=hostile,
                    sender_email="a@gmail.com", message=hostile),
        ):
            assert "<script>" not in html and "<a href" not in html
            assert "&lt;script&gt;" in html

    def test_enquiry_alert_shows_sender_name_email_and_message(self):
        """TC-EML-TPL-003 | AC-09.1 | T10 | positive | the admin alert carries sender name, email and message, and says so when there is no message"""
        context = dict(listing_title="Racket", owner_name="Omar", sender_name="Ann", sender_email="ann@gmail.com")
        with_message = _render("enquiry_admin.html", message="Is it free on Sunday?", **context)
        assert "Ann" in with_message and "ann@gmail.com" in with_message and "Is it free on Sunday?" in with_message
        assert "(no message)" in _render("enquiry_admin.html", message=None, **context)

    def test_a_missing_template_variable_fails_instead_of_rendering_blank(self):
        """TC-EML-TPL-004 | AC-18.2 | T16 | negative | forgetting a variable raises; it never sends 'Hi ,'"""
        with pytest.raises(UndefinedError):
            _render("welcome.html")


class TestAdapterSelection:
    def test_console_is_the_default(self):
        """TC-EML-ADP-001 | AC-19.1 | T03 | positive | with no email settings the console adapter is used"""
        assert isinstance(get_adapter(), ConsoleEmailAdapter)

    @pytest.mark.parametrize("key, sender", [("", "noreply@infyexchange.test"), ("a-key", ""), ("", "")])
    def test_brevo_without_credentials_falls_back_to_console_and_warns(self, monkeypatch, caplog, key, sender):
        """TC-EML-ADP-002 | AC-19.1 | T03 | negative | EMAIL_PROVIDER=brevo with a missing key or sender uses the console adapter and logs a warning"""
        monkeypatch.setattr(settings, "email_provider", "brevo")
        monkeypatch.setattr(settings, "email_api_key", key)
        monkeypatch.setattr(settings, "sender_email", sender)
        with caplog.at_level(logging.WARNING, logger="app.services.email_service"):
            adapter = get_adapter()
        assert isinstance(adapter, ConsoleEmailAdapter)
        assert "EMAIL_API_KEY or SENDER_EMAIL" in caplog.text

    def test_brevo_with_credentials_uses_the_brevo_adapter(self, brevo):
        """TC-EML-ADP-003 | AC-19.1 | T03 | positive | a key and a sender select the Brevo adapter"""
        assert isinstance(get_adapter(), BrevoEmailAdapter)

    def test_an_unknown_provider_stops_the_app_at_startup(self):
        """TC-EML-ADP-004 | AC-19.1 | T03 | negative | EMAIL_PROVIDER=sendgrid is a settings error, not a silent no-op"""
        from pydantic import ValidationError

        from app.config import Settings

        with pytest.raises(ValidationError):
            Settings(
                database_url="sqlite:///x.db", secret_key="x", cloudinary_cloud_name="a",
                cloudinary_api_key="b", cloudinary_api_secret="c", email_provider="sendgrid",
            )


class TestConsoleAdapter:
    def test_logs_recipient_subject_and_a_body_preview(self, caplog):
        """TC-EML-CON-001 | AC-19.1 | T03 | positive | the console adapter prints the recipient, subject and a truncated body"""
        body = "<p>" + "x" * 1000 + "</p>"
        with caplog.at_level(logging.INFO, logger="app.services.email_service"):
            asyncio.run(ConsoleEmailAdapter().send(_message(html=body)))
        assert "ann@gmail.com" in caplog.text and "Hello" in caplog.text
        assert "x" * 250 in caplog.text and "x" * 400 not in caplog.text


class TestBrevoAdapter:
    def _send(self, brevo, message):
        return asyncio.run(get_adapter().send(message))

    def test_posts_the_documented_request(self, brevo):
        """TC-EML-BRV-001 | AC-19.1 | T03 | positive | one POST to the API path with the api-key header and sender, to, subject and htmlContent"""
        self._send(brevo, _message())
        (request,) = brevo.requests
        assert request["path"] == "/v3/smtp/email"
        assert request["headers"]["api-key"] == "test-api-key"
        assert request["headers"]["accept"] == "application/json"
        assert request["json"] == {
            "sender": {"email": "noreply@infyexchange.test", "name": settings.app_name},
            "to": [{"email": "ann@gmail.com", "name": "Ann"}],
            "subject": "Hello",
            "htmlContent": "<p>Hi</p>",
        }

    def test_reply_to_is_sent_only_when_given(self, brevo):
        """TC-EML-BRV-002 | AC-09.1 | T10 | positive | replyTo carries the given address and name; it is absent otherwise"""
        self._send(brevo, _message(reply_to_email="bob@gmail.com", reply_to_name="Bob"))
        self._send(brevo, _message(to_name=None))
        with_reply, without = brevo.requests
        assert with_reply["json"]["replyTo"] == {"email": "bob@gmail.com", "name": "Bob"}
        assert "replyTo" not in without["json"] and without["json"]["to"] == [{"email": "ann@gmail.com"}]

    def test_a_rejection_raises_with_status_and_code_but_no_address(self, brevo):
        """TC-EML-BRV-003 | AC-19.1 | T03 | negative | a 4xx raises EmailDeliveryError naming the HTTP status and Brevo's code, without the recipient"""
        brevo.status, brevo.reply = 401, {"code": "unauthorized", "message": "Key not found for ann@gmail.com"}
        with pytest.raises(EmailDeliveryError) as raised:
            self._send(brevo, _message())
        text = str(raised.value)
        assert "401" in text and "unauthorized" in text and "ann@gmail.com" not in text

    def test_a_non_json_server_error_still_raises(self, brevo):
        """TC-EML-BRV-004 | AC-19.1 | T03 | negative | a 500 whose body is not JSON raises with code=None"""
        brevo.status, brevo.reply = 500, {}
        with pytest.raises(EmailDeliveryError, match="HTTP 500"):
            self._send(brevo, _message())

    def test_an_unreachable_provider_raises(self, brevo):
        """TC-EML-BRV-005 | AC-19.1 | T03 | negative | a refused connection raises EmailDeliveryError rather than hanging or being swallowed"""
        brevo.stop()
        with pytest.raises(EmailDeliveryError, match="Could not reach Brevo"):
            self._send(brevo, _message())


class TestRegistrationEmail:
    def test_registration_sends_a_welcome_email(self, client, brevo):
        """TC-EML-REG-001 | AC-01.1 | T05 | positive | a successful registration sends one welcome email to the new user, greeting them by name"""
        payload = register_payload("welcome@gmail.com")
        payload["name"] = "Asha Rao"
        assert client.post(REGISTER, json=payload).status_code == 201
        (request,) = brevo.requests
        assert request["json"]["to"] == [{"email": "welcome@gmail.com", "name": "Asha Rao"}]
        assert request["json"]["subject"] == "Welcome to InfyExchange"
        assert "Hi Asha Rao," in request["json"]["htmlContent"]

    def test_a_rejected_registration_sends_nothing(self, client, brevo):
        """TC-EML-REG-002 | AC-01.3 | T05 | negative | validation failures and duplicates send no email"""
        assert client.post(REGISTER, json=register_payload("dupe@gmail.com")).status_code == 201
        brevo.requests.clear()
        assert client.post(REGISTER, json=register_payload("dupe@gmail.com")).status_code == 409
        assert client.post(REGISTER, json={**register_payload("bad@gmail.com"), "phone": "1" * 15}).status_code == 422
        assert brevo.requests == []

    def test_with_no_provider_registration_works_and_the_email_goes_to_the_log(self, client, caplog):
        """TC-EML-REG-003 | AC-01.1 | T05 | positive | in console mode registration succeeds and the welcome email is printed, not sent anywhere"""
        with caplog.at_level(logging.INFO, logger="app.services.email_service"):
            assert client.post(REGISTER, json=register_payload("local@gmail.com")).status_code == 201
        assert "EMAIL (console)" in caplog.text and "Welcome to InfyExchange" in caplog.text

    def test_a_provider_failure_is_loud_and_the_email_is_kept(self, client, db_session, brevo):
        """TC-EML-REG-004 | AC-01.1 | T05 | negative | when Brevo refuses, the error is raised (not swallowed), the account still exists, and the email is stored for an admin"""
        brevo.status, brevo.reply = 500, {"code": "internal_error"}
        with pytest.raises(EmailDeliveryError):
            client.post(REGISTER, json=register_payload("kept@gmail.com"))
        assert db_session.scalar(select(User).where(User.email == "kept@gmail.com")) is not None
        (row,) = db_session.scalars(select(FailedEmail)).all()
        assert (row.to_email, row.subject, row.attempts) == ("kept@gmail.com", "Welcome to InfyExchange", 1)
        assert "HTTP 500" in row.error and "kept@gmail.com" not in row.error


class TestEnquiryAlert:
    def _enquire(self, client, db, message="Is it free on Sunday?", **listing_fields):
        owner, buyer = make_user(db), make_user(db)
        listing = add_listing(db, owner, title="Yonex racket", **listing_fields)
        buyer.name = "Ann Buyer"
        db.commit()
        response = client.post(f"{ENQUIRE}/{listing.id}", json={"message": message}, headers=auth_headers(buyer))
        return owner, buyer, response

    def test_an_enquiry_alerts_the_admin_with_reply_to_the_enquirer(self, client, db_session, brevo):
        """TC-EML-ENQ-001 | AC-09.1 | T10 | positive | one alert goes to ADMIN_EMAIL, replyTo is the enquirer, and the body has the item, sender and message"""
        owner, buyer, response = self._enquire(client, db_session)
        assert response.status_code == 201
        (request,) = brevo.requests
        body = request["json"]
        assert body["to"] == [{"email": "admin@infyexchange.test"}]
        assert body["replyTo"] == {"email": buyer.email, "name": "Ann Buyer"}
        assert body["subject"] == "New enquiry: Yonex racket"
        for expected in ("Yonex racket", owner.name, "Ann Buyer", buyer.email, "Is it free on Sunday?"):
            assert expected in body["htmlContent"]

    def test_the_alert_never_contains_the_owners_contact_details(self, client, db_session, brevo):
        """TC-EML-ENQ-002 | AC-10.4 | T13 | business | the enquirer's address is in the alert (the reply-to needs it); the item owner's email and phone are not"""
        owner, _, _ = self._enquire(client, db_session)
        html = brevo.requests[0]["json"]["htmlContent"]
        assert owner.email not in html and owner.phone not in html

    def test_a_hostile_message_cannot_inject_markup(self, client, db_session, brevo):
        """TC-EML-ENQ-003 | AC-18.2 | T16 | negative | HTML in an enquiry message arrives escaped in the admin's email"""
        self._enquire(client, db_session, message="<img src=x onerror=alert(1)>")
        html = brevo.requests[0]["json"]["htmlContent"]
        assert "<img" not in html and "&lt;img" in html

    def test_no_admin_email_means_a_warning_and_no_send(self, client, db_session, brevo, monkeypatch, caplog):
        """TC-EML-ENQ-004 | AC-09.1 | T10 | negative | with ADMIN_EMAIL empty the enquiry still succeeds, nothing is sent, and a warning is logged"""
        monkeypatch.setattr(settings, "admin_email", "")
        with caplog.at_level(logging.WARNING, logger="app.services.email_service"):
            _, _, response = self._enquire(client, db_session)
        assert response.status_code == 201
        assert brevo.requests == [] and "ADMIN_EMAIL is not set" in caplog.text

    def test_a_refused_enquiry_sends_no_alert(self, client, db_session, brevo):
        """TC-EML-ENQ-005 | AC-09.2 | T10 | negative | an enquiry on your own item or a duplicate enquiry sends no alert"""
        owner = make_user(db_session)
        listing = add_listing(db_session, owner)
        assert client.post(f"{ENQUIRE}/{listing.id}", json={}, headers=auth_headers(owner)).status_code == 400
        buyer = make_user(db_session)
        assert client.post(f"{ENQUIRE}/{listing.id}", json={}, headers=auth_headers(buyer)).status_code == 201
        brevo.requests.clear()
        assert client.post(f"{ENQUIRE}/{listing.id}", json={}, headers=auth_headers(buyer)).status_code == 409
        assert brevo.requests == []

    def test_a_provider_failure_is_loud_and_the_alert_is_kept(self, client, db_session, brevo):
        """TC-EML-ENQ-006 | AC-09.1 | T10 | negative | when Brevo refuses the alert the error is raised, the enquiry still exists, and the alert is stored"""
        from app.models import Interest

        brevo.status = 401
        owner, buyer = make_user(db_session), make_user(db_session)
        listing = add_listing(db_session, owner)
        with pytest.raises(EmailDeliveryError):
            client.post(f"{ENQUIRE}/{listing.id}", json={}, headers=auth_headers(buyer))
        assert db_session.scalar(select(Interest).where(Interest.listing_id == listing.id)) is not None
        (row,) = db_session.scalars(select(FailedEmail)).all()
        assert row.to_email == "admin@infyexchange.test" and row.reply_to_email == buyer.email


class TestAdminFailedEmails:
    def test_admin_lists_failed_emails_newest_first(self, client, db_session):
        """TC-EML-ADM-001 | AC-13.1 | T12 | positive | the list shows recipient, subject, error and attempts, newest first"""
        admin = make_user(db_session, is_admin=True)
        old = _add_failed(db_session, created_at=datetime.utcnow() - timedelta(days=2), subject="older")
        new = _add_failed(db_session, subject="newer")
        body = client.get(ADMIN, headers=auth_headers(admin)).json()
        assert body["total"] == 2
        assert [item["id"] for item in body["items"]] == [new.id, old.id]
        assert set(body["items"][0]) == {"id", "to_email", "subject", "error", "attempts", "created_at", "last_attempt_at"}

    def test_only_admins_can_see_or_act_on_them(self, client, db_session):
        """TC-EML-ADM-002 | AC-13.2 | T12 | negative | a normal user gets 403 and an anonymous caller 401/403 on list, retry and discard"""
        user = make_user(db_session)
        row = _add_failed(db_session)
        for method, url in (("get", ADMIN), ("post", f"{ADMIN}/{row.id}/retry"), ("delete", f"{ADMIN}/{row.id}")):
            assert getattr(client, method)(url, headers=auth_headers(user)).status_code == 403
            assert getattr(client, method)(url).status_code in (401, 403)
        assert db_session.get(FailedEmail, row.id) is not None

    def test_retry_sends_the_stored_message_and_removes_it(self, client, db_session, brevo):
        """TC-EML-ADM-003 | AC-13.1 | T12 | positive | a successful retry re-sends exactly the stored email, deletes the row and is audited without the address"""
        admin = make_user(db_session, is_admin=True)
        row = _add_failed(db_session, reply_to_email="bob@gmail.com", reply_to_name="Bob")
        row_id = row.id
        response = client.post(f"{ADMIN}/{row_id}/retry", headers=auth_headers(admin))
        assert response.status_code == 200
        (request,) = brevo.requests
        assert request["json"]["to"] == [{"email": "ann@gmail.com", "name": "Ann"}]
        assert request["json"]["htmlContent"] == "<p>Hi Ann</p>"
        assert request["json"]["replyTo"] == {"email": "bob@gmail.com", "name": "Bob"}
        db_session.expire_all()
        assert db_session.get(FailedEmail, row_id) is None
        (audit,) = db_session.scalars(select(AuditLog).where(AuditLog.action == "RETRY_EMAIL")).all()
        assert audit.target_id == str(row_id) and '"sent"' in audit.details and "ann@gmail.com" not in audit.details

    def test_a_retry_that_fails_again_keeps_the_row_and_says_so(self, client, db_session, brevo):
        """TC-EML-ADM-004 | AC-13.1 | T12 | negative | when the provider refuses again the answer is 502, attempts goes up, the row stays and the attempt is audited"""
        brevo.status, brevo.reply = 500, {"code": "internal_error"}
        admin = make_user(db_session, is_admin=True)
        row = _add_failed(db_session)
        response = client.post(f"{ADMIN}/{row.id}/retry", headers=auth_headers(admin))
        assert response.status_code == 502
        db_session.expire_all()
        kept = db_session.get(FailedEmail, row.id)
        assert kept is not None and kept.attempts == 2 and "HTTP 500" in kept.error
        (audit,) = db_session.scalars(select(AuditLog).where(AuditLog.action == "RETRY_EMAIL")).all()
        assert '"failed"' in audit.details

    def test_retry_is_refused_when_no_provider_is_configured(self, client, db_session):
        """TC-EML-ADM-005 | AC-13.1 | T12 | negative | in console mode retry is 409 and the row is kept, so nothing is 'sent' to the log and lost"""
        admin = make_user(db_session, is_admin=True)
        row = _add_failed(db_session)
        assert client.post(f"{ADMIN}/{row.id}/retry", headers=auth_headers(admin)).status_code == 409
        assert db_session.get(FailedEmail, row.id) is not None

    def test_discard_removes_the_row_and_is_audited(self, client, db_session):
        """TC-EML-ADM-006 | AC-13.1 | T12 | positive | discard deletes the row without sending and writes an audit entry"""
        admin = make_user(db_session, is_admin=True)
        row_id = _add_failed(db_session).id
        assert client.delete(f"{ADMIN}/{row_id}", headers=auth_headers(admin)).status_code == 200
        db_session.expire_all()
        assert db_session.get(FailedEmail, row_id) is None
        assert db_session.scalars(select(AuditLog).where(AuditLog.action == "DISCARD_EMAIL")).all()

    def test_unknown_ids_are_404(self, client, db_session, brevo):
        """TC-EML-ADM-007 | AC-13.1 | T12 | negative | retry or discard of a missing email is 404"""
        admin = make_user(db_session, is_admin=True)
        assert client.post(f"{ADMIN}/999999/retry", headers=auth_headers(admin)).status_code == 404
        assert client.delete(f"{ADMIN}/999999", headers=auth_headers(admin)).status_code == 404

    def test_cleanup_drops_unresolved_failures_after_thirty_days(self, db_session):
        """TC-EML-ADM-008 | AC-14.1 | T15 | business | the daily cleanup deletes failed emails older than 30 days (they hold an address and message) and keeps newer ones"""
        old = _add_failed(db_session, created_at=datetime.utcnow() - timedelta(days=31))
        recent = _add_failed(db_session, created_at=datetime.utcnow() - timedelta(days=29))
        old_id, recent_id = old.id, recent.id
        cleanup_expired_data()
        db_session.expire_all()
        assert db_session.get(FailedEmail, old_id) is None
        assert db_session.get(FailedEmail, recent_id) is not None
