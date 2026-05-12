"""Unit tests for `like_spotify.auth.google`.

Slice: #28 — the OAuth flow itself is exercised only at its
`requests.post` boundary; the loopback HTTP callback + browser open
flow needs real OS surfaces and lives behind an integration test.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from like_spotify.auth import google as google_auth
from like_spotify.core.errors import AuthError, TransientError


# ── Token persistence ──────────────────────────────────────────────────


def test_save_and_load_tokens_roundtrip(tmp_path) -> None:
    path = tmp_path / "google.json"
    google_auth.save_tokens(path, {"refresh_token": "rt", "access_token": "at"})
    loaded = google_auth.load_tokens(path)
    assert loaded["refresh_token"] == "rt"
    assert loaded["access_token"] == "at"


def test_load_tokens_missing_returns_empty_dict(tmp_path) -> None:
    assert google_auth.load_tokens(tmp_path / "missing.json") == {}


def test_load_tokens_corrupt_returns_empty_dict(tmp_path) -> None:
    path = tmp_path / "google.json"
    path.write_text("{not-json")
    assert google_auth.load_tokens(path) == {}


# ── make_token_provider() ──────────────────────────────────────────────


def _write_tokens(path: Path, **overrides) -> None:
    base = {
        "access_token": "at-cached",
        "refresh_token": "rt",
        "expires_at": time.time() + 3600,
        "client_id": "cid",
        "client_secret": "sec",
    }
    base.update(overrides)
    google_auth.save_tokens(path, base)


def test_provider_returns_cached_token_when_not_expired(tmp_path) -> None:
    path = tmp_path / "g.json"
    _write_tokens(path)
    provider = google_auth.make_token_provider(path)
    assert provider() == "at-cached"


def test_provider_refreshes_when_expired(tmp_path, monkeypatch) -> None:
    path = tmp_path / "g.json"
    _write_tokens(path, expires_at=time.time() - 10)

    fake_response = MagicMock(status_code=200)
    fake_response.json.return_value = {"access_token": "at-fresh", "expires_in": 3600}
    post = MagicMock(return_value=fake_response)
    monkeypatch.setattr(google_auth.requests, "post", post)

    provider = google_auth.make_token_provider(path)
    token = provider()

    assert token == "at-fresh"
    post.assert_called_once()
    body = post.call_args.kwargs["data"]
    assert body["grant_type"] == "refresh_token"
    assert body["refresh_token"] == "rt"
    assert body["client_id"] == "cid"
    assert body["client_secret"] == "sec"

    # New token is persisted, so a second call doesn't hit the network.
    post.reset_mock()
    assert provider() == "at-fresh"
    post.assert_not_called()


def test_provider_no_refresh_token_raises_authn_error(tmp_path) -> None:
    path = tmp_path / "g.json"
    google_auth.save_tokens(path, {})
    provider = google_auth.make_token_provider(path)
    with pytest.raises(AuthError, match="not authenticated"):
        provider()


def test_provider_refresh_400_raises_auth_error(tmp_path, monkeypatch) -> None:
    path = tmp_path / "g.json"
    _write_tokens(path, expires_at=time.time() - 10)

    post = MagicMock(return_value=MagicMock(status_code=400, text="bad refresh"))
    monkeypatch.setattr(google_auth.requests, "post", post)

    provider = google_auth.make_token_provider(path)
    with pytest.raises(AuthError, match="rejected"):
        provider()


def test_provider_refresh_5xx_raises_transient(tmp_path, monkeypatch) -> None:
    path = tmp_path / "g.json"
    _write_tokens(path, expires_at=time.time() - 10)

    post = MagicMock(return_value=MagicMock(status_code=503, text="oops"))
    monkeypatch.setattr(google_auth.requests, "post", post)

    provider = google_auth.make_token_provider(path)
    with pytest.raises(TransientError):
        provider()


def test_provider_missing_client_secret_in_store_raises(tmp_path) -> None:
    """Token store written by an older flow has no client_id/secret —
    refresh needs them, so we tell the user how to recover."""
    path = tmp_path / "g.json"
    _write_tokens(path, expires_at=time.time() - 10, client_id="", client_secret="")
    provider = google_auth.make_token_provider(path)
    with pytest.raises(AuthError, match="--reauth"):
        provider()


# ── authorize() input validation ───────────────────────────────────────


def test_authorize_rejects_empty_client_id(tmp_path) -> None:
    with pytest.raises(ValueError, match="client_id"):
        google_auth.authorize(
            client_id="", client_secret="sec", token_path=tmp_path / "g.json"
        )


def test_authorize_rejects_empty_client_secret(tmp_path) -> None:
    with pytest.raises(ValueError, match="client_secret"):
        google_auth.authorize(
            client_id="cid", client_secret="", token_path=tmp_path / "g.json"
        )
