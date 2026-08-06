"""LikeCooldownGate / LikeCooldownRecorder — default flavor cooldown dedup.

Guards against accidentally counting the same track as liked twice (e.g.
two hotkey presses seconds apart) by skipping the like when the track was
already liked within a configurable cooldown window (default 10 minutes).
Mirrors the mobile app's `SharedPrefsLikeCountRepository` cooldown design
(`getLastLikedAt` / `recordLikedAt`): local-only, no Storage/network
round-trip — cross-device dedup was deliberately descoped as
overengineering, so this reads/writes a small JSON file under the config
dir instead.

Two cooperating actions sharing one `_CooldownStore`, split the same way
the mobile repository splits the check from the record:
    - `LikeCooldownGate` (PreLikeAction) — runs before the real like; a
      track liked within the window returns `False`, aborting the like
      with "Skipped by LikeCooldownGate" feedback (see
      `Pipeline.run_once`).
    - `LikeCooldownRecorder` (PostLikeAction) — runs after
      `MusicProvider.like` succeeds, stamping the current time. Recording
      only on confirmed success (not from the gate) means a failed like
      never starts the cooldown, so a genuine retry isn't blocked.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from like_spotify.core.actions import PostLikeAction, PreLikeAction
from like_spotify.core.types import LikeContext

DOMAIN = "like_cooldown"
DEFAULT_MINUTES = 10

logger = logging.getLogger(__name__)


class _CooldownStore:
    """Local JSON map of `track_id -> last_liked_at (unix seconds)`."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def last_liked_at(self, track_id: str) -> float | None:
        return self._load().get(track_id)

    def record(self, track_id: str, at: float) -> None:
        state = self._load()
        state[track_id] = at
        self._save(state)

    def _load(self) -> dict[str, float]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, state: dict[str, float]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(state), encoding="utf-8")
        except OSError:
            logger.warning("like-cooldown: failed to persist state to %s", self._path)


class LikeCooldownGate(PreLikeAction):
    def __init__(self, store: _CooldownStore, minutes: int = DEFAULT_MINUTES) -> None:
        if minutes < 1:
            raise ValueError("minutes must be >= 1")
        self._store = store
        self._window_seconds = minutes * 60

    async def run(self, ctx: LikeContext) -> bool:
        last = self._store.last_liked_at(ctx.track.provider_track_id)
        if last is not None and (time.time() - last) < self._window_seconds:
            return False
        return True


class LikeCooldownRecorder(PostLikeAction):
    def __init__(self, store: _CooldownStore) -> None:
        self._store = store

    async def run(self, ctx: LikeContext) -> None:
        self._store.record(ctx.track.provider_track_id, time.time())


def build_like_cooldown(
    state_path: Path, minutes: int = DEFAULT_MINUTES
) -> tuple[LikeCooldownGate, LikeCooldownRecorder]:
    """Factory called by the host. Returns the (pre, post) action pair —
    both must be wired into the same `Pipeline` to share cooldown state."""
    store = _CooldownStore(state_path)
    return LikeCooldownGate(store, minutes=minutes), LikeCooldownRecorder(store)
