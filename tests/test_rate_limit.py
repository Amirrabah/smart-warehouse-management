"""The login rate limit must count real clients, also behind Railway's proxy.

Behind a proxy every request comes from the proxy's IP, so 5 failed logins by anyone would lock
out everyone. The proxy appends the real client IP as the LAST X-Forwarded-For entry. Earlier
entries are sent by the client and can be faked, so only the last one is trusted.
"""

import pytest
from starlette.requests import Request

from app.config import settings
from app.rate_limit import client_ip


def make_request(client: str = "10.0.0.1", forwarded_for: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return Request({"type": "http", "headers": headers, "client": (client, 50000)})


@pytest.fixture
def behind_proxy(monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)


def test_trust_is_off_by_default():
    assert settings.trust_proxy_headers is False


def test_without_proxy_the_socket_address_is_used():
    request = make_request(client="10.0.0.1", forwarded_for="1.2.3.4")

    assert client_ip(request) == "10.0.0.1"  # header ignored: anyone could send it


def test_behind_proxy_the_last_forwarded_address_is_used(behind_proxy):
    request = make_request(client="100.64.0.2", forwarded_for="6.6.6.6, 203.0.113.7")

    assert client_ip(request) == "203.0.113.7"  # 6.6.6.6 was sent by the client: ignored


def test_behind_proxy_single_forwarded_address(behind_proxy):
    assert client_ip(make_request(forwarded_for=" 203.0.113.7 ")) == "203.0.113.7"


def test_behind_proxy_without_header_falls_back_to_socket(behind_proxy):
    assert client_ip(make_request(client="10.0.0.9")) == "10.0.0.9"


def test_behind_proxy_empty_entries_are_skipped(behind_proxy):
    assert client_ip(make_request(forwarded_for="203.0.113.7, ,")) == "203.0.113.7"


def login(client, forwarded_for: str):
    return client.post(
        "/auth/login",
        json={"email": "nobody@test.local", "password": "wrong"},
        headers={"X-Forwarded-For": forwarded_for},
    )


def test_behind_proxy_one_client_cannot_lock_out_another(client, behind_proxy):
    for _ in range(5):
        assert login(client, "198.51.100.1").status_code == 401

    assert login(client, "198.51.100.1").status_code == 429
    assert login(client, "198.51.100.2").status_code == 401  # someone else can still try


def test_behind_proxy_faking_earlier_entries_does_not_reset_the_limit(client, behind_proxy):
    for n in range(5):
        assert login(client, f"10.9.9.{n}, 198.51.100.1").status_code == 401

    assert login(client, "10.9.9.99, 198.51.100.1").status_code == 429
