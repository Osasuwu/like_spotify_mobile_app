"""Smoke tests for the tracer-bullet pipeline (#21).

Network / keyboard / tray are not exercised — we mock the MusicProvider
and verify the core composition flows the way the host depends on.
"""

from __future__ import annotations

import pytest

from like_spotify.core.music_provider import MusicProvider
from like_spotify.core.pipeline import Pipeline
from like_spotify.core.types import CurrentTrack


class FakeProvider(MusicProvider):
    def __init__(self, track: CurrentTrack | None, like_raises: Exception | None = None):
        self._track = track
        self._like_raises = like_raises
        self.like_calls: list[CurrentTrack] = []

    async def get_currently_playing(self) -> CurrentTrack | None:
        return self._track

    async def like(self, track: CurrentTrack) -> None:
        if self._like_raises is not None:
            raise self._like_raises
        self.like_calls.append(track)

    async def user_id(self) -> str:
        return "user-id"


class Feedback:
    def __init__(self) -> None:
        self.calls: list[tuple[bool, str, str]] = []

    def __call__(self, success: bool, title: str, message: str) -> None:
        self.calls.append((success, title, message))


@pytest.mark.asyncio
async def test_like_path_calls_provider_and_emits_success() -> None:
    track = CurrentTrack(
        provider="spotify",
        provider_track_id="abc123",
        title="Song",
        artists=("Artist",),
    )
    provider = FakeProvider(track=track)
    fb = Feedback()

    await Pipeline(provider=provider, feedback=fb).run_once()

    assert provider.like_calls == [track]
    assert len(fb.calls) == 1
    success, title, _ = fb.calls[0]
    assert success is True
    assert title == "Liked"


@pytest.mark.asyncio
async def test_nothing_playing_skips_like() -> None:
    provider = FakeProvider(track=None)
    fb = Feedback()

    await Pipeline(provider=provider, feedback=fb).run_once()

    assert provider.like_calls == []
    assert fb.calls == [(False, "Nothing playing", "")]


@pytest.mark.asyncio
async def test_like_failure_surfaces_to_feedback() -> None:
    track = CurrentTrack(
        provider="spotify", provider_track_id="x", title="t", artists=()
    )
    provider = FakeProvider(track=track, like_raises=RuntimeError("boom"))
    fb = Feedback()

    await Pipeline(provider=provider, feedback=fb).run_once()

    assert provider.like_calls == []
    assert len(fb.calls) == 1
    success, title, message = fb.calls[0]
    assert success is False
    assert title == "Like failed"
    assert "boom" in message
