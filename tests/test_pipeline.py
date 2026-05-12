"""Smoke tests for the pipeline (#21) + Storage wiring (#22).

Network / keyboard / tray are not exercised — we mock MusicProvider +
Storage and verify the core composition flows the way the host depends on.
"""

from __future__ import annotations

import pytest

from like_spotify.core.music_provider import MusicProvider
from like_spotify.core.pipeline import Pipeline
from like_spotify.core.storage import Storage
from like_spotify.core.types import CurrentTrack


class FakeProvider(MusicProvider):
    def __init__(
        self,
        track: CurrentTrack | None,
        like_raises: Exception | None = None,
        user: str = "user-id",
    ):
        self._track = track
        self._like_raises = like_raises
        self._user = user
        self.like_calls: list[CurrentTrack] = []
        self.user_id_calls = 0

    async def get_currently_playing(self) -> CurrentTrack | None:
        return self._track

    async def like(self, track: CurrentTrack) -> None:
        if self._like_raises is not None:
            raise self._like_raises
        self.like_calls.append(track)

    async def user_id(self) -> str:
        self.user_id_calls += 1
        return self._user


class FakeStorage(Storage):
    def __init__(self, counts: dict[tuple[str, str], int] | None = None,
                 raises: Exception | None = None):
        self._counts = counts or {}
        self._raises = raises
        self.increment_calls: list[tuple[str, str]] = []

    async def increment(self, user_id: str, track: CurrentTrack) -> int:
        if self._raises is not None:
            raise self._raises
        key = (user_id, track.provider_track_id)
        self.increment_calls.append(key)
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def get_count(self, user_id: str, track: CurrentTrack) -> int:
        return self._counts.get((user_id, track.provider_track_id), 0)


class Feedback:
    def __init__(self) -> None:
        self.calls: list[tuple[bool, str, str]] = []

    def __call__(self, success: bool, title: str, message: str) -> None:
        self.calls.append((success, title, message))


def _track(track_id: str = "abc123") -> CurrentTrack:
    return CurrentTrack(
        provider="spotify",
        provider_track_id=track_id,
        title="Song",
        artists=("Artist",),
    )


@pytest.mark.asyncio
async def test_like_path_calls_provider_and_emits_success() -> None:
    provider = FakeProvider(track=_track())
    fb = Feedback()

    await Pipeline(provider=provider, feedback=fb).run_once()

    assert provider.like_calls == [_track()]
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
    provider = FakeProvider(track=_track(), like_raises=RuntimeError("boom"))
    fb = Feedback()

    await Pipeline(provider=provider, feedback=fb).run_once()

    assert provider.like_calls == []
    assert len(fb.calls) == 1
    success, title, message = fb.calls[0]
    assert success is False
    assert title == "Like failed"
    assert "boom" in message


@pytest.mark.asyncio
async def test_storage_increment_count_surfaces_in_title() -> None:
    provider = FakeProvider(track=_track())
    storage = FakeStorage()
    fb = Feedback()

    await Pipeline(provider=provider, feedback=fb, storage=storage).run_once()
    await Pipeline(provider=provider, feedback=fb, storage=storage).run_once()
    await Pipeline(provider=provider, feedback=fb, storage=storage).run_once()

    assert storage.increment_calls == [("user-id", "abc123")] * 3
    assert [c[1] for c in fb.calls] == ["Liked × 1", "Liked × 2", "Liked × 3"]


@pytest.mark.asyncio
async def test_storage_failure_does_not_fail_like() -> None:
    provider = FakeProvider(track=_track())
    storage = FakeStorage(raises=RuntimeError("supabase down"))
    fb = Feedback()

    await Pipeline(provider=provider, feedback=fb, storage=storage).run_once()

    assert provider.like_calls == [_track()]
    success, title, _ = fb.calls[0]
    assert success is True
    assert title == "Liked"  # no count suffix on soft fail


@pytest.mark.asyncio
async def test_storage_not_called_when_like_fails() -> None:
    provider = FakeProvider(track=_track(), like_raises=RuntimeError("nope"))
    storage = FakeStorage()
    fb = Feedback()

    await Pipeline(provider=provider, feedback=fb, storage=storage).run_once()

    assert storage.increment_calls == []
