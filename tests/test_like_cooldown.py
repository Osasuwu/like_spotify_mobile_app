"""Tests for LikeCooldownGate / LikeCooldownRecorder (like-cooldown dedup)."""

from __future__ import annotations

import json

import pytest

from like_spotify.core.types import CurrentTrack, LikeContext
from like_spotify.extensions.like_cooldown import (
    LikeCooldownGate,
    LikeCooldownRecorder,
    _CooldownStore,
    build_like_cooldown,
)


def _track(track_id: str = "trk-a") -> CurrentTrack:
    return CurrentTrack(
        provider="spotify",
        provider_track_id=track_id,
        title="Song",
        artists=("Artist",),
    )


def _ctx(track_id: str = "trk-a") -> LikeContext:
    return LikeContext(track=_track(track_id))


@pytest.mark.asyncio
async def test_gate_allows_first_like(tmp_path) -> None:
    store = _CooldownStore(tmp_path / "cooldown.json")
    gate = LikeCooldownGate(store, minutes=10)

    assert await gate.run(_ctx()) is True


@pytest.mark.asyncio
async def test_gate_blocks_repeat_within_window(tmp_path) -> None:
    store = _CooldownStore(tmp_path / "cooldown.json")
    gate = LikeCooldownGate(store, minutes=10)
    recorder = LikeCooldownRecorder(store)

    ctx = _ctx()
    assert await gate.run(ctx) is True
    await recorder.run(ctx)

    # Same track, immediately again — still inside the 10 minute window.
    assert await gate.run(_ctx()) is False


@pytest.mark.asyncio
async def test_gate_allows_after_window_elapses(tmp_path, monkeypatch) -> None:
    import like_spotify.extensions.like_cooldown as mod

    store = _CooldownStore(tmp_path / "cooldown.json")
    gate = LikeCooldownGate(store, minutes=10)
    recorder = LikeCooldownRecorder(store)

    base_time = 1_000_000.0
    monkeypatch.setattr(mod.time, "time", lambda: base_time)

    ctx = _ctx()
    await recorder.run(ctx)
    assert await gate.run(_ctx()) is False

    # Advance past the 10 minute window.
    monkeypatch.setattr(mod.time, "time", lambda: base_time + 601)
    assert await gate.run(_ctx()) is True


@pytest.mark.asyncio
async def test_gate_is_per_track(tmp_path) -> None:
    store = _CooldownStore(tmp_path / "cooldown.json")
    gate = LikeCooldownGate(store, minutes=10)
    recorder = LikeCooldownRecorder(store)

    ctx_a = _ctx("trk-a")
    await recorder.run(ctx_a)
    assert await gate.run(_ctx("trk-a")) is False
    # A different track is unaffected by trk-a's cooldown.
    assert await gate.run(_ctx("trk-b")) is True


@pytest.mark.asyncio
async def test_persistence_across_store_instances(tmp_path) -> None:
    path = tmp_path / "cooldown.json"
    store1 = _CooldownStore(path)
    recorder = LikeCooldownRecorder(store1)
    await recorder.run(_ctx())

    # Fresh store instance pointed at the same file picks up prior state.
    store2 = _CooldownStore(path)
    gate = LikeCooldownGate(store2, minutes=10)
    assert await gate.run(_ctx()) is False


@pytest.mark.asyncio
async def test_missing_state_file_is_noop(tmp_path) -> None:
    store = _CooldownStore(tmp_path / "does-not-exist.json")
    gate = LikeCooldownGate(store, minutes=10)

    assert await gate.run(_ctx()) is True


@pytest.mark.asyncio
async def test_corrupt_state_file_does_not_crash(tmp_path) -> None:
    path = tmp_path / "cooldown.json"
    path.write_text("{not valid json", encoding="utf-8")
    store = _CooldownStore(path)
    gate = LikeCooldownGate(store, minutes=10)

    assert await gate.run(_ctx()) is True


def test_gate_constructor_validates_minutes(tmp_path) -> None:
    store = _CooldownStore(tmp_path / "cooldown.json")
    with pytest.raises(ValueError):
        LikeCooldownGate(store, minutes=0)
    with pytest.raises(ValueError):
        LikeCooldownGate(store, minutes=-5)


@pytest.mark.asyncio
async def test_build_like_cooldown_pair_shares_state(tmp_path) -> None:
    path = tmp_path / "cooldown.json"
    gate, recorder = build_like_cooldown(path, minutes=10)

    ctx = _ctx()
    assert await gate.run(ctx) is True
    await recorder.run(ctx)
    assert await gate.run(_ctx()) is False
    assert json.loads(path.read_text(encoding="utf-8"))["trk-a"] > 0
