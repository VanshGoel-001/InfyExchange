"""Unit tests: rupee formatting, name rules and plain-text previews, plus where the name rule is applied."""

import pytest

from app.utils.money import format_price, format_rupees
from app.utils.names import clean_name, is_valid_name, plain_preview
from tests.conftest import register_payload

REGISTER = "/api/auth/register"


@pytest.mark.parametrize(
    "amount, expected",
    [
        (0, "₹0"), (5, "₹5"), (999, "₹999"), (1000, "₹1,000"), (12345, "₹12,345"), (99999, "₹99,999"),
        (100000, "₹1,00,000"), (123456, "₹1,23,456"), (1234567, "₹12,34,567"), (10_000_000, "₹1,00,00,000"),
        (-1500, "-₹1,500"),
    ],
)
def test_rupees_use_indian_grouping(amount, expected):
    """TC-UTL-MON-001 | AC-07.4 | T08 | boundary | ₹ with lakh/crore grouping across every digit boundary"""
    assert format_rupees(amount) == expected


def test_price_text_matches_the_spa():
    """TC-UTL-MON-002 | AC-07.4 | T08 | positive | zero is Free; a unit is appended; no unit adds nothing"""
    assert format_price(0) == "Free"
    assert format_price(1500, "day") == "₹1,500 / day"
    assert format_price(2500) == "₹2,500"


@pytest.mark.parametrize(
    "name", ["Asha Rao", "O'Brien", "Anne-Marie", "A. R. Rahman", "Dr. Strange", "Zoë Ångström", "आशा राव", "Jean d’Arc"],
)
def test_ordinary_names_are_accepted(name):
    """TC-UTL-NAM-001 | AC-01.2 | T05 | positive | letters in any script, spaces and . ' ’ - are fine"""
    assert is_valid_name(name)


@pytest.mark.parametrize(
    "name",
    ["<b>Asha</b>", "Asha > Rao", "Asha123", "Asha_Rao", "http://evil.com", "see www.evil.com", "evil.com", "a@b.com",
     "Asha/Rao", "Asha;DROP", "", "   ", "Asha (admin)"],
)
def test_names_with_markup_digits_or_links_are_refused(name):
    """TC-UTL-NAM-002 | AC-01.2 | T05 | negative | < > digits, symbols and link-like text are not names"""
    assert not is_valid_name(name)


def test_clean_name_makes_outside_names_safe():
    """TC-UTL-NAM-003 | AC-21.1 | T05 | business | clean_name drops link words and stray characters and keeps the readable name"""
    assert clean_name("<b>Asha</b> Rao 123") == "bAshab Rao"
    assert clean_name("Asha Rao https://evil.com/x") == "Asha Rao"
    assert clean_name("www.evil.com") == ""
    assert clean_name("A" * 150, limit=100) == "A" * 100


def test_previews_replace_links_and_are_clipped():
    """TC-UTL-NAM-004 | AC-10.1 | T10 | business | links become the word link; text is flattened and clipped; markup stays as plain characters"""
    assert plain_preview("see https://example.com/a/b?c=1 now") == "see link now"
    assert plain_preview("go to www.evil.com or evil.org/page") == "go to link or link"
    assert plain_preview("a\n\n  b") == "a b"
    assert plain_preview("<script>x</script>") == "<script>x</script>"
    assert len(plain_preview("word " * 100, 80)) <= 80


class TestRegistrationNames:
    @pytest.mark.parametrize("name", ["<b>x</b> Rao", "Asha1 Rao", "visit www.evil.com", "Asha > Rao"])
    def test_register_refuses_bad_names(self, client, name):
        """TC-API-REG-040 | AC-01.2 | T05 | negative | sign-up with < > digits or a link in the name is a 422 and no account is made"""
        payload = register_payload("badname@gmail.com") | {"name": name}
        assert client.post(REGISTER, json=payload).status_code == 422

    def test_register_accepts_a_normal_name(self, client):
        """TC-API-REG-041 | AC-01.2 | T05 | positive | an apostrophe and hyphen are allowed"""
        payload = register_payload("goodname@gmail.com") | {"name": "Mary-Ann O'Neil"}
        assert client.post(REGISTER, json=payload).status_code == 201
