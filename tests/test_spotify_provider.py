"""Contract tests for SpotifyMusicProvider — slice-scoped to #24.

We don't re-test the OAuth flow here; just the read-side calls the
pipeline added on this slice: `is_liked` against `/me/tracks/contains`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from like_spotify.core.types import CurrentTrack
from like_spotify.extensions.spotify import SpotifyMusicProvider


@dataclass
class FakeResponse:
    status_code: int
    text: str = ""
    json_body: Any = None
    headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {}

    def json(self) -> Any:
        return self.json_body


def _provider(tmp_path) -> SpotifyMusicProvider:
    """Build a provider with a primed access token to skip auth refresh."""
    import time

    token_path = tmp_path / "token.json"
    p = SpotifyMusicProvider(client_id="cid", token_path=token_path)
    # Inject a non-expired access token so _access_token() short-circuits.
    p._tokens = {
        "access_token": "test-token",
        "refresh_token": "rt",
        "expires_at": time.time() + 3600,
    }
    return p


def _track(track_id: str = "trk1") -> CurrentTrack:
    return CurrentTrack(
        provider="spotify", provider_track_id=track_id, title="t", artists=("a",)
    )


@pytest.mark.asyncio
async def test_is_liked_true(monkeypatch, tmp_path) -> None:
    captured: dict[str, Any] = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return FakeResponse(status_code=200, json_body=[True])

    monkeypatch.setattr("like_spotify.extensions.spotify.requests.get", fake_get)

    p = _provider(tmp_path)
    assert await p.is_liked(_track("trk-42")) is True
    assert captured["url"].endswith("/me/tracks/contains")
    assert captured["params"] == {"ids": "trk-42"}


@pytest.mark.asyncio
async def test_is_liked_false(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "like_spotify.extensions.spotify.requests.get",
        lambda *a, **kw: FakeResponse(status_code=200, json_body=[False]),
    )
    p = _provider(tmp_path)
    assert await p.is_liked(_track()) is False


@pytest.mark.asyncio
async def test_is_liked_empty_body_treated_as_false(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "like_spotify.extensions.spotify.requests.get",
        lambda *a, **kw: FakeResponse(status_code=200, json_body=[]),
    )
    p = _provider(tmp_path)
    assert await p.is_liked(_track()) is False
