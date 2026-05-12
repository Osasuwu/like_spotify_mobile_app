"""Setup wizard + storage dispatch tests.

Slice: #28 (one-liner install + interactive --setup + autostart).

Covers the wizard branches (re-runnable, --reauth, storage backend
choice, autostart) and the multi-backend `build_storage` dispatch.
The real OAuth flows (Spotify PKCE, Google installed-app) are not
exercised — they hit a real browser + network; the wizard mocks the
provider/storage factories at their boundaries.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from like_spotify.hosts import _common


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def tmp_paths(tmp_path, monkeypatch) -> Iterator[Path]:
    """Redirect all host I/O at a writable tmp dir."""
    cfg = tmp_path / "config.json"
    spotify = tmp_path / "spotify_token.json"
    google = tmp_path / "google_token.json"
    monkeypatch.setattr(_common, "CONFIG_FILE", cfg)
    monkeypatch.setattr(_common, "SPOTIFY_TOKEN_FILE", spotify)
    monkeypatch.setattr(_common, "GOOGLE_TOKEN_FILE", google)
    yield tmp_path


class _FakeProvider:
    """Stand-in for SpotifyMusicProvider used during setup."""

    def __init__(self, has_tokens: bool = False) -> None:
        self._has = has_tokens
        self.authorize_calls = 0

    @property
    def has_tokens(self) -> bool:
        return self._has

    def authorize(self) -> None:
        self.authorize_calls += 1
        self._has = True


@pytest.fixture
def fake_provider(monkeypatch) -> _FakeProvider:
    fp = _FakeProvider()
    monkeypatch.setattr(_common, "make_provider", lambda _client_id: fp)
    return fp


def _scripted_input(answers: list[str]):
    """Returns a callable substitute for `input` that pops answers in order.

    If the wizard prompts more than scripted, fail fast — that's a real
    drift in the wizard, not a test bug.
    """
    answers = list(answers)

    def _input(prompt: str = "") -> str:
        if not answers:
            raise AssertionError(f"wizard asked for more input than scripted: {prompt!r}")
        return answers.pop(0)

    return _input


# ── do_setup happy path: Spotify + Supabase + no autostart ─────────────


def test_setup_supabase_writes_config_and_runs_oauth(
    tmp_paths, fake_provider, monkeypatch
) -> None:
    answers = [
        "abc123client",        # Spotify Client ID
        "supabase",            # Storage backend
        "https://x.supabase.co",  # Supabase URL
        "anon-key-xyz",        # Supabase anon key
        # autostart prompt only fires on win32 — we patch sys.platform off
    ]
    monkeypatch.setattr("builtins.input", _scripted_input(answers))
    monkeypatch.setattr(_common.sys, "platform", "darwin")

    rc = _common.do_setup(reauth=False)
    assert rc == 0

    cfg = _common.load_config()
    assert cfg["spotify"]["client_id"] == "abc123client"
    assert cfg["storage"]["backend"] == "supabase"
    assert cfg["supabase"]["url"] == "https://x.supabase.co"
    assert cfg["supabase"]["anon_key"] == "anon-key-xyz"
    assert fake_provider.authorize_calls == 1


def test_setup_skips_spotify_oauth_when_tokens_present(
    tmp_paths, monkeypatch
) -> None:
    fp = _FakeProvider(has_tokens=True)
    monkeypatch.setattr(_common, "make_provider", lambda _cid: fp)
    monkeypatch.setattr("builtins.input", _scripted_input([
        "abc123client",
        "none",
    ]))
    monkeypatch.setattr(_common.sys, "platform", "linux")

    rc = _common.do_setup(reauth=False)
    assert rc == 0
    assert fp.authorize_calls == 0  # tokens already there


def test_setup_reauth_forces_oauth_even_with_tokens(
    tmp_paths, monkeypatch
) -> None:
    fp = _FakeProvider(has_tokens=True)
    monkeypatch.setattr(_common, "make_provider", lambda _cid: fp)
    monkeypatch.setattr("builtins.input", _scripted_input([
        "abc123client",
        "none",
    ]))
    monkeypatch.setattr(_common.sys, "platform", "linux")

    rc = _common.do_setup(reauth=True)
    assert rc == 0
    assert fp.authorize_calls == 1


def test_setup_aborts_when_client_id_missing(
    tmp_paths, fake_provider, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("builtins.input", _scripted_input([""]))
    monkeypatch.setattr(_common.sys, "platform", "linux")

    rc = _common.do_setup(reauth=False)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Client ID is required" in err


def test_setup_storage_none_writes_backend_marker(
    tmp_paths, fake_provider, monkeypatch
) -> None:
    monkeypatch.setattr("builtins.input", _scripted_input([
        "abc123client",
        "none",
    ]))
    monkeypatch.setattr(_common.sys, "platform", "linux")

    rc = _common.do_setup(reauth=False)
    assert rc == 0
    cfg = _common.load_config()
    assert cfg["storage"]["backend"] == "none"
    # No supabase / sheets blocks created.
    assert "supabase" not in cfg or not cfg.get("supabase")
    assert "sheets" not in cfg or not cfg.get("sheets")


def test_setup_aborts_when_supabase_creds_blank(
    tmp_paths, fake_provider, monkeypatch, capsys
) -> None:
    monkeypatch.setattr("builtins.input", _scripted_input([
        "abc123client",
        "supabase",
        "",  # empty URL
        "",  # empty anon key
    ]))
    monkeypatch.setattr(_common.sys, "platform", "linux")

    rc = _common.do_setup(reauth=False)
    assert rc == 2
    assert "supabase" in capsys.readouterr().err.lower()


def test_setup_sheets_branch_runs_google_oauth(
    tmp_paths, fake_provider, monkeypatch
) -> None:
    monkeypatch.setattr("builtins.input", _scripted_input([
        "abc123client",
        "sheets",
        "spreadsheet-id-xyz",
        "google-client.apps.googleusercontent.com",
        "google-secret",
    ]))
    monkeypatch.setattr(_common.sys, "platform", "linux")

    calls: dict = {}

    def fake_google_authorize(*, client_id, client_secret, token_path):
        calls["client_id"] = client_id
        calls["client_secret"] = client_secret
        calls["token_path"] = token_path
        # Pretend the OAuth flow wrote a refresh token to disk.
        token_path.write_text('{"refresh_token": "rt", "access_token": "at"}')
        return {"refresh_token": "rt", "access_token": "at"}

    monkeypatch.setattr(_common.google_auth, "authorize", fake_google_authorize)

    rc = _common.do_setup(reauth=False)
    assert rc == 0

    cfg = _common.load_config()
    assert cfg["storage"]["backend"] == "sheets"
    assert cfg["sheets"]["spreadsheet_id"] == "spreadsheet-id-xyz"
    assert calls["client_id"] == "google-client.apps.googleusercontent.com"
    assert calls["client_secret"] == "google-secret"
    assert calls["token_path"] == _common.GOOGLE_TOKEN_FILE


def test_setup_sheets_skips_google_oauth_when_refresh_token_present(
    tmp_paths, fake_provider, monkeypatch
) -> None:
    """If google_token.json already has a refresh_token, the wizard should
    not re-prompt for client_id/secret and not call `authorize`."""
    _common.GOOGLE_TOKEN_FILE.write_text(
        '{"refresh_token": "rt", "access_token": "at",'
        ' "client_id": "old", "client_secret": "old"}'
    )

    monkeypatch.setattr("builtins.input", _scripted_input([
        "abc123client",
        "sheets",
        "spreadsheet-id-xyz",
        # NO client_id/secret prompts because refresh_token is present.
    ]))
    monkeypatch.setattr(_common.sys, "platform", "linux")

    called = {"n": 0}

    def fake_google_authorize(**_kw):
        called["n"] += 1

    monkeypatch.setattr(_common.google_auth, "authorize", fake_google_authorize)

    rc = _common.do_setup(reauth=False)
    assert rc == 0
    assert called["n"] == 0


# ── build_storage dispatch ─────────────────────────────────────────────


def test_build_storage_supabase_backend(tmp_paths) -> None:
    storage = _common.build_storage({
        "storage": {"backend": "supabase"},
        "supabase": {"url": "https://x.supabase.co", "anon_key": "k"},
    })
    assert storage is not None
    assert type(storage).__name__ == "SupabaseStorage"


def test_build_storage_supabase_back_compat_legacy_config(tmp_paths) -> None:
    """Configs written before #28 only have a `supabase` block, no
    `storage.backend` marker. They must keep working."""
    storage = _common.build_storage({
        "supabase": {"url": "https://x.supabase.co", "anon_key": "k"},
    })
    assert storage is not None
    assert type(storage).__name__ == "SupabaseStorage"


def test_build_storage_supabase_back_compat_env_vars_only(
    tmp_paths, monkeypatch
) -> None:
    """Pre-#28: only env vars (no config block at all) was a supported
    deploy path. The dispatcher must keep that working."""
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "k")
    storage = _common.build_storage({})
    assert storage is not None
    assert type(storage).__name__ == "SupabaseStorage"


def test_build_storage_sheets_backend(tmp_paths) -> None:
    _common.GOOGLE_TOKEN_FILE.write_text(
        '{"refresh_token": "rt", "access_token": "at",'
        ' "expires_at": 9999999999,'
        ' "client_id": "cid", "client_secret": "sec"}'
    )
    storage = _common.build_storage({
        "storage": {"backend": "sheets"},
        "sheets": {"spreadsheet_id": "sid"},
    })
    assert storage is not None
    assert type(storage).__name__ == "GoogleSheetsStorage"


def test_build_storage_none_backend_returns_none(tmp_paths) -> None:
    assert _common.build_storage({"storage": {"backend": "none"}}) is None


def test_build_storage_missing_supabase_creds_returns_none(tmp_paths) -> None:
    """Acceptance criterion #22: like still succeeds when storage is
    unconfigured. The host must not crash on a half-filled supabase block."""
    assert (
        _common.build_storage({
            "storage": {"backend": "supabase"},
            "supabase": {"url": ""},
        })
        is None
    )


def test_build_storage_missing_spreadsheet_id_returns_none(tmp_paths) -> None:
    assert _common.build_storage({"storage": {"backend": "sheets"}}) is None


# ── print_config_paths surfaces all three paths ────────────────────────


def test_print_config_paths_includes_google_token(tmp_paths, capsys) -> None:
    rc = _common.print_config_paths()
    assert rc == 0
    out = capsys.readouterr().out
    assert "Config:" in out
    assert "Spotify token:" in out
    assert "Google token:" in out
