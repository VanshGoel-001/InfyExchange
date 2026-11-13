"""Service tests: in-memory sliding-window rate limiter and key helpers (task T13)."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import rate_limit
from app.services.rate_limit import (
    InMemoryRateLimiter,
    account_key,
    client_key,
    rate_limit_dependency,
)


class _Clock:
    """Controllable replacement for the ``time`` module used by rate_limit."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def time(self) -> float:
        return self.now


@pytest.fixture()
def clock(monkeypatch):
    fake = _Clock()
    monkeypatch.setattr(rate_limit, "time", fake)
    return fake


class TestSlidingWindow:
    def test_allows_up_to_the_limit_then_blocks(self, clock):
        """TC-SVC-RLM-001 | AC-15.1 | T13 | boundary | exactly max_requests are allowed; the next one is blocked"""
        limiter = InMemoryRateLimiter(3, 60, "t")
        assert [limiter.is_allowed("k") for _ in range(3)] == [True, True, True]
        assert limiter.is_allowed("k") is False

    def test_keys_are_independent(self, clock):
        """TC-SVC-RLM-002 | AC-15.1 | T13 | business | exhausting one key does not affect another"""
        limiter = InMemoryRateLimiter(1, 60, "t")
        assert limiter.is_allowed("a") is True
        assert limiter.is_allowed("a") is False
        assert limiter.is_allowed("b") is True

    def test_request_just_inside_window_is_still_counted(self, clock):
        """TC-SVC-RLM-003 | AC-15.1 | T13 | boundary | 59.9 s after the first request the slot is still taken"""
        limiter = InMemoryRateLimiter(1, 60, "t")
        assert limiter.is_allowed("k") is True
        clock.now += 59.9
        assert limiter.is_allowed("k") is False

    def test_request_exactly_at_window_edge_is_allowed(self, clock):
        """TC-SVC-RLM-004 | AC-15.1 | T13 | boundary | exactly one full window later the slot is free again"""
        limiter = InMemoryRateLimiter(1, 60, "t")
        assert limiter.is_allowed("k") is True
        clock.now += 60
        assert limiter.is_allowed("k") is True

    def test_blocked_requests_do_not_extend_the_window(self, clock):
        """TC-SVC-RLM-005 | AC-15.1 | T13 | business | rejected attempts are not recorded, so the block ends on schedule"""
        limiter = InMemoryRateLimiter(1, 60, "t")
        assert limiter.is_allowed("k") is True
        clock.now += 30
        assert limiter.is_allowed("k") is False
        clock.now += 30
        assert limiter.is_allowed("k") is True


class TestEnforce:
    def test_enforce_returns_none_when_allowed(self, clock):
        """TC-SVC-RLM-010 | AC-15.1 | T13 | positive | enforce() is silent while under the limit"""
        assert InMemoryRateLimiter(1, 60, "t").enforce("k", "slow down") is None

    def test_enforce_raises_429_with_retry_after(self, clock):
        """TC-SVC-RLM-011 | AC-15.1 | T13 | negative | over the limit: 429, supplied detail, Retry-After = window"""
        limiter = InMemoryRateLimiter(1, 45, "t")
        limiter.enforce("k", "slow down")
        with pytest.raises(HTTPException) as caught:
            limiter.enforce("k", "slow down")
        assert caught.value.status_code == 429
        assert caught.value.detail == "slow down"
        assert caught.value.headers["Retry-After"] == "45"

    def test_dependency_enforces_per_client_and_scope(self, clock):
        """TC-SVC-RLM-012 | AC-15.1 | T13 | business | the dependency keys by '<scope>:<ip>'"""
        limiter = InMemoryRateLimiter(1, 60, "t")
        dependency = rate_limit_dependency(limiter, "admin", "too many")
        request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"))
        dependency(request)
        with pytest.raises(HTTPException):
            dependency(request)
        other_ip = SimpleNamespace(client=SimpleNamespace(host="10.0.0.2"))
        dependency(other_ip)  # different client is unaffected


class TestKeyHelpers:
    def test_client_key_uses_scope_and_ip(self):
        """TC-SVC-RLM-020 | AC-15.1 | T13 | positive | key format is '<scope>:<client ip>'"""
        request = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"))
        assert client_key(request, "login") == "login:203.0.113.9"

    def test_client_key_without_client_falls_back_to_unknown(self):
        """TC-SVC-RLM-021 | AC-15.1 | T13 | boundary | a request with no client address maps to 'unknown'"""
        assert client_key(SimpleNamespace(client=None), "login") == "login:unknown"

    def test_account_key_is_hashed_and_case_insensitive(self):
        """TC-SVC-RLM-022 | AC-15.2 | T13 | business | the account key hides the email and ignores case"""
        key = account_key("Person@Gmail.com")
        assert key.startswith("acct:")
        assert "person" not in key.lower()
        assert "gmail" not in key.lower()
        assert key == account_key("person@gmail.com")

    def test_account_key_differs_between_accounts(self):
        """TC-SVC-RLM-023 | AC-15.2 | T13 | negative | different emails never share a key"""
        assert account_key("a@gmail.com") != account_key("b@gmail.com")
