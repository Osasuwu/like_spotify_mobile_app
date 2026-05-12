"""Contract tests for SupabaseStorage (#22).

HTTP layer is stubbed via `monkeypatch` on `requests`. No real network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from like_spotify.core.errors import TransientError
from like_spotify.core.types import CurrentTrack
from like_spotify.extensions.supabase_storage import SupabaseStorage


@dataclass
class FakeResponse:
    status_code: int
    text: str = ""
    json_body: Any = None

    def json(self) -> Any:
        return self.json_body


def _track(track_id: str = "trk1") -> CurrentTrack:
    return CurrentTrack(
        provider="spotify", provider_track_id=track_id, title="t", artists=("a",)
    )


def test_constructor_rejects_empty_creds() -> None:
    with pytest.raises(ValueError):
        SupabaseStorage(url="", anon_key="k")
    with pytest.raises(ValueError):
        SupabaseStorage(url="https://x.supabase.co", anon_key="")


@pytest.mark.asyncio
async def test_increment_posts_to_rpc_and_returns_count(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse(status_code=200, text="7\n")

    monkeypatch.setattr(
        "like_spotify.extensions.supabase_storage.requests.post", fake_post
    )

    storage = SupabaseStorage(url="https://x.supabase.co/", anon_key="anonkey")
    count = await storage.increment("user-1", _track("trk-42"))

    assert count == 7
    assert captured["url"] == "https://x.supabase.co/rest/v1/rpc/increment_track_like"
    assert captured["json"] == {
        "p_user_id": "user-1",
        "p_track_id": "trk-42",
        "p_was_already_liked": False,
    }
    h = captured["headers"]
    assert h["apikey"] == "anonkey"
    assert h["Authorization"] == "Bearer anonkey"


@pytest.mark.asyncio
async def test_increment_passes_was_already_liked_flag(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse(status_code=200, text="2")

    monkeypatch.setattr(
        "like_spotify.extensions.supabase_storage.requests.post", fake_post
    )

    storage = SupabaseStorage(url="https://x.supabase.co", anon_key="k")
    count = await storage.increment("user-1", _track(), was_already_liked=True)

    assert count == 2
    assert captured["json"]["p_was_already_liked"] is True


@pytest.mark.asyncio
async def test_increment_5xx_raises_transient(monkeypatch) -> None:
    monkeypatch.setattr(
        "like_spotify.extensions.supabase_storage.requests.post",
        lambda *a, **kw: FakeResponse(status_code=503, text="upstream"),
    )
    storage = SupabaseStorage(url="https://x.supabase.co", anon_key="k")
    with pytest.raises(TransientError):
        await storage.increment("user-1", _track())


@pytest.mark.asyncio
async def test_increment_4xx_raises_runtime(monkeypatch) -> None:
    monkeypatch.setattr(
        "like_spotify.extensions.supabase_storage.requests.post",
        lambda *a, **kw: FakeResponse(status_code=400, text="bad request"),
    )
    storage = SupabaseStorage(url="https://x.supabase.co", anon_key="k")
    with pytest.raises(RuntimeError):
        await storage.increment("user-1", _track())


@pytest.mark.asyncio
async def test_get_count_returns_row_value(monkeypatch) -> None:
    monkeypatch.setattr(
        "like_spotify.extensions.supabase_storage.requests.get",
        lambda *a, **kw: FakeResponse(status_code=200, json_body=[{"count": 12}]),
    )
    storage = SupabaseStorage(url="https://x.supabase.co", anon_key="k")
    assert await storage.get_count("user-1", _track()) == 12


@pytest.mark.asyncio
async def test_get_count_zero_when_no_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        "like_spotify.extensions.supabase_storage.requests.get",
        lambda *a, **kw: FakeResponse(status_code=200, json_body=[]),
    )
    storage = SupabaseStorage(url="https://x.supabase.co", anon_key="k")
    assert await storage.get_count("user-1", _track()) == 0
