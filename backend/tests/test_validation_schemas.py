"""Validation tests: Pydantic request schemas and the 422 error contract (task T16, plus schema tasks T05, T08, T10, T11).

Schemas are exercised directly (fast, exhaustive boundaries); a few API-level checks confirm how
those failures are reported to clients.
"""

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.interest import InterestCreate
from app.schemas.listing import ListingUpdate
from app.schemas.need import NeedCreate
from tests.conftest import register_payload


REGISTER_BASE = dict(name="Asha", email="asha@gmail.com", phone="9876543210", password="Passw0rd1", role="SE", joining_date="2026-01-01")
NEED_BASE = dict(title="Racket", category="SQUASH", need_type="BUY", location="ECC", description="Need one")


def _register(**overrides):
    return RegisterRequest(**{**REGISTER_BASE, **overrides})


def _need(**overrides):
    return NeedCreate(**{**NEED_BASE, **overrides})


class TestRegisterRequestSchema:
    @pytest.mark.parametrize("name, ok", [("A", False), ("AB", True), ("A" * 100, True), ("A" * 101, False), ("", False)])
    def test_name_length(self, name, ok):
        """TC-VAL-REG-001 | AC-01.5 | T05 | boundary | name must be 2-100 characters"""
        if ok:
            assert _register(name=name).name == name
        else:
            with pytest.raises(ValidationError):
                _register(name=name)

    @pytest.mark.parametrize("phone, ok", [("1" * 9, False), ("1" * 10, True), ("1" * 15, True), ("1" * 16, False)])
    def test_phone_length(self, phone, ok):
        """TC-VAL-REG-002 | AC-01.5 | T05 | boundary | phone must be 10-15 characters"""
        if ok:
            _register(phone=phone)
        else:
            with pytest.raises(ValidationError):
                _register(phone=phone)

    @pytest.mark.parametrize(
        "password, ok",
        [
            ("Pass0rd", False),            # 7 chars
            ("Passw0rd", True),            # 8 chars (minimum)
            ("a" * 99 + "1", True),        # 100 chars (maximum)
            ("a" * 100 + "1", False),      # 101 chars
            ("12345678", False),           # digits only
            ("abcdefgh", False),           # letters only
            ("abcdefg1", True),            # smallest valid mix
            ("        ", False),           # whitespace only
        ],
    )
    def test_password_rules(self, password, ok):
        """TC-VAL-REG-003 | AC-01.4 | T05 | boundary | password 8-100 characters with at least one letter and one digit"""
        if ok:
            _register(password=password)
        else:
            with pytest.raises(ValidationError):
                _register(password=password)

    @pytest.mark.parametrize("email", ["plain", "a@", "@gmail.com", "a b@gmail.com", ""])
    def test_malformed_email_is_rejected(self, email):
        """TC-VAL-REG-004 | AC-01.2 | T05 | negative | strings that are not email addresses fail validation"""
        with pytest.raises(ValidationError):
            _register(email=email)

    @pytest.mark.parametrize("role", ["SE", "DSE", "SP_L1", "SP_L2"])
    def test_every_role_is_accepted(self, role):
        """TC-VAL-REG-005 | AC-01.5 | T05 | positive | all four defined roles are valid"""
        assert _register(role=role).role.value == role

    @pytest.mark.parametrize("role", ["ADMIN", "se", "", "Manager"])
    def test_unknown_role_is_rejected(self, role):
        """TC-VAL-REG-006 | AC-01.5 | T05 | negative | undefined roles (including wrong case) are rejected"""
        with pytest.raises(ValidationError):
            _register(role=role)

    @pytest.mark.parametrize("value", ["2026-13-01", "2026-02-30", "yesterday", "", "01/02/2026"])
    def test_invalid_joining_date_is_rejected(self, value):
        """TC-VAL-REG-007 | AC-01.5 | T05 | negative | impossible or non-ISO dates are rejected"""
        with pytest.raises(ValidationError):
            _register(joining_date=value)

    @pytest.mark.parametrize("missing", ["name", "email", "phone", "password", "role", "joining_date"])
    def test_every_field_is_required(self, missing):
        """TC-VAL-REG-008 | AC-01.5 | T05 | negative | omitting any single field fails validation"""
        data = {k: v for k, v in REGISTER_BASE.items() if k != missing}
        with pytest.raises(ValidationError):
            RegisterRequest(**data)


class TestLoginRequestSchema:
    def test_password_may_be_exactly_100_characters(self):
        """TC-VAL-LOG-001 | AC-02.2 | T05 | boundary | 100-character password is accepted by the schema"""
        assert LoginRequest(email="a@gmail.com", password="p" * 100)

    def test_password_over_100_is_rejected(self):
        """TC-VAL-LOG-002 | AC-02.2 | T05 | boundary | 101 characters fails"""
        with pytest.raises(ValidationError):
            LoginRequest(email="a@gmail.com", password="p" * 101)

    def test_login_does_not_apply_registration_password_policy(self):
        """TC-VAL-LOG-003 | AC-02.2 | T05 | business | a short, letters-only password is not a schema error at login (it simply fails authentication)"""
        assert LoginRequest(email="a@gmail.com", password="abc")


class TestNeedCreateSchema:
    @pytest.mark.parametrize("field, length, ok", [
        ("title", 1, False), ("title", 2, True), ("title", 150, True), ("title", 151, False),
        ("location", 1, False), ("location", 2, True), ("location", 100, True), ("location", 101, False),
        ("description", 1, False), ("description", 2, True), ("description", 2000, True), ("description", 2001, False),
        ("duration", 100, True), ("duration", 101, False),
    ])
    def test_text_length_boundaries(self, field, length, ok):
        """TC-VAL-NED-001 | AC-08.2 | T11 | boundary | title 2-150, location 2-100, description 2-2000, duration <= 100"""
        if ok:
            assert _need(**{field: "x" * length})
        else:
            with pytest.raises(ValidationError):
                _need(**{field: "x" * length})

    @pytest.mark.parametrize("budget, ok", [(-1, False), (0, True), (1, True), (10**9, True)])
    def test_budget_must_not_be_negative(self, budget, ok):
        """TC-VAL-NED-002 | AC-08.2 | T11 | boundary | budget >= 0"""
        if ok:
            assert _need(budget=budget).budget == budget
        else:
            with pytest.raises(ValidationError):
                _need(budget=budget)

    def test_defaults(self):
        """TC-VAL-NED-003 | AC-08.2 | T11 | positive | budget defaults to 0 and duration to None"""
        need = _need()
        assert need.budget == 0 and need.duration is None

    @pytest.mark.parametrize("overrides", [{"need_type": "TRADE"}, {"category": "GOLF"}, {"need_type": "buy"}])
    def test_enum_values_are_case_sensitive_and_closed(self, overrides):
        """TC-VAL-NED-004 | AC-08.2 | T11 | negative | undefined or wrongly-cased enum values are rejected"""
        with pytest.raises(ValidationError):
            _need(**overrides)


class TestListingUpdateSchema:
    def test_all_fields_are_optional(self):
        """TC-VAL-LST-001 | AC-07.1 | T08 | boundary | an empty update is valid and carries no fields"""
        assert ListingUpdate().model_dump(exclude_unset=True) == {}

    @pytest.mark.parametrize("title, ok", [("a", False), ("ab", True), ("x" * 150, True), ("x" * 151, False)])
    def test_title_length(self, title, ok):
        """TC-VAL-LST-002 | AC-07.3 | T08 | boundary | title 2-150 characters when supplied"""
        if ok:
            assert ListingUpdate(title=title).title == title
        else:
            with pytest.raises(ValidationError):
                ListingUpdate(title=title)

    @pytest.mark.parametrize("price, ok", [(-1, False), (0, True), (1, True)])
    def test_price_not_negative(self, price, ok):
        """TC-VAL-LST-003 | AC-07.3 | T08 | boundary | price >= 0 when supplied"""
        if ok:
            assert ListingUpdate(price=price).price == price
        else:
            with pytest.raises(ValidationError):
                ListingUpdate(price=price)

    @pytest.mark.parametrize("overrides", [{"status": "DELETED"}, {"condition": "BROKEN"}, {"price": "free"}])
    def test_invalid_values_are_rejected(self, overrides):
        """TC-VAL-LST-004 | AC-07.3 | T08 | negative | unknown enum values and non-numeric price fail"""
        with pytest.raises(ValidationError):
            ListingUpdate(**overrides)

    def test_only_supplied_fields_are_reported(self):
        """TC-VAL-LST-005 | AC-07.1 | T08 | business | exclude_unset yields just the fields the client sent"""
        assert ListingUpdate(title="New title", price=5).model_dump(exclude_unset=True) == {"title": "New title", "price": 5}


class TestInterestCreateSchema:
    @pytest.mark.parametrize("length, ok", [(0, True), (500, True), (501, False)])
    def test_message_length(self, length, ok):
        """TC-VAL-INT-001 | AC-09.1 | T10 | boundary | message of 0-500 characters is accepted, 501 is not"""
        if ok:
            assert InterestCreate(message="m" * length)
        else:
            with pytest.raises(ValidationError):
                InterestCreate(message="m" * length)

    def test_message_defaults_to_none(self):
        """TC-VAL-INT-002 | AC-09.1 | T10 | positive | omitting the message is valid"""
        assert InterestCreate().message is None


class TestValidationErrorContract:
    def test_single_error_is_a_string_naming_the_field(self, client):
        """TC-VAL-ERR-001 | AC-18.1 | T16 | positive | one invalid field gives 422 with detail as a single 'field: message' string"""
        payload = register_payload("one@gmail.com", password="short1")
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, str)
        assert detail.startswith("password")

    def test_multiple_errors_are_a_list(self, client):
        """TC-VAL-ERR-002 | AC-18.1 | T16 | positive | several invalid fields give 422 with detail as a list of messages"""
        response = client.post("/api/auth/register", json={})
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, list) and len(detail) >= 2
        assert any(item.startswith("email") for item in detail)

    def test_error_body_never_echoes_submitted_password(self, client):
        """TC-VAL-ERR-003 | AC-18.1 | T16 | business | validation messages do not repeat the password the client sent"""
        secret = "OnlyLetters"
        response = client.post("/api/auth/register", json=register_payload("leak@gmail.com", password=secret))
        assert secret not in response.text

    def test_query_validation_errors_use_same_format(self, client):
        """TC-VAL-ERR-004 | AC-18.1 | T16 | positive | an out-of-range query parameter is a 422 whose detail names it"""
        response = client.get("/api/listings", params={"limit": 0})
        assert response.status_code == 422
        assert "limit" in str(response.json()["detail"])

    def test_malformed_json_body_is_422_not_500(self, client):
        """TC-VAL-ERR-005 | AC-18.1 | T16 | negative | invalid JSON gets a client error, never a server error"""
        response = client.post("/api/auth/login", content="{not json", headers={"Content-Type": "application/json"})
        assert response.status_code == 422
