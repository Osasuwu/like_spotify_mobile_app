"""Supabase Storage — default flavor cross-device counter.

Wraps the `increment_track_like` RPC (returns the new total) and a
SELECT on `track_likes` for `get_count`. Sync `requests` wrapped in
`asyncio.to_thread`, mirroring the SpotifyMusicProvider style.

Canonical schema lives in `docs/supabase-setup.sql`. Summary:
    table  track_likes(
        user_id text, track_id text, count int, backfilled bool,
        primary key(user_id, track_id))
    func   increment_track_like(
        p_user_id text, p_track_id text, p_was_already_liked bool default false)
        returns int   -- inserts (count=2, backfilled=true) if flag is true on
                      -- first encounter; plain +1 on every subsequent press.
"""

from __future__ import annotations

import asyncio

import requests

from like_spotify.core.errors import TransientError
from like_spotify.core.storage import Storage
from like_spotify.core.types import CurrentTrack

DOMAIN = "supabase"


class SupabaseStorage(Storage):
    def __init__(self, url: str, anon_key: str, timeout: float = 5.0) -> None:
        if not url or not anon_key:
            raise ValueError("supabase url and anon_key are required")
        self._url = url.rstrip("/")
        self._key = anon_key
        self._timeout = timeout

    async def increment(
        self,
        user_id: str,
        track: CurrentTrack,
        was_already_liked: bool = False,
    ) -> int:
        return await asyncio.to_thread(
            self._increment_sync,
            user_id,
            track.provider_track_id,
            was_already_liked,
        )

    async def get_count(self, user_id: str, track: CurrentTrack) -> int:
        return await asyncio.to_thread(self._get_count_sync, user_id, track.provider_track_id)

    async def record_artist_track(
        self, user_id: str, artist_id: str, track_id: str
    ) -> int:
        return await asyncio.to_thread(
            self._record_artist_track_sync, user_id, artist_id, track_id
        )

    # ── Internals ────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
        }

    def _increment_sync(
        self,
        user_id: str,
        track_id: str,
        was_already_liked: bool,
    ) -> int:
        r = requests.post(
            f"{self._url}/rest/v1/rpc/increment_track_like",
            headers=self._headers(),
            json={
                "p_user_id": user_id,
                "p_track_id": track_id,
                "p_was_already_liked": was_already_liked,
            },
            timeout=self._timeout,
        )
        if r.status_code >= 500:
            raise TransientError(f"supabase rpc 5xx: {r.status_code}")
        if r.status_code >= 400:
            raise RuntimeError(f"supabase rpc {r.status_code}: {r.text}")
        return _parse_count(r.text)

    def _record_artist_track_sync(
        self, user_id: str, artist_id: str, track_id: str
    ) -> int:
        r = requests.post(
            f"{self._url}/rest/v1/rpc/record_artist_track",
            headers=self._headers(),
            json={
                "p_user_id": user_id,
                "p_artist_id": artist_id,
                "p_track_id": track_id,
            },
            timeout=self._timeout,
        )
        if r.status_code >= 500:
            raise TransientError(f"supabase rpc 5xx: {r.status_code}")
        if r.status_code >= 400:
            raise RuntimeError(f"supabase rpc {r.status_code}: {r.text}")
        return _parse_count(r.text)

    def _get_count_sync(self, user_id: str, track_id: str) -> int:
        r = requests.get(
            f"{self._url}/rest/v1/track_likes",
            headers=self._headers(),
            params={
                "select": "count",
                "user_id": f"eq.{user_id}",
                "track_id": f"eq.{track_id}",
                "limit": "1",
            },
            timeout=self._timeout,
        )
        if r.status_code >= 500:
            raise TransientError(f"supabase select 5xx: {r.status_code}")
        if r.status_code >= 400:
            raise RuntimeError(f"supabase select {r.status_code}: {r.text}")
        rows = r.json()
        if not rows:
            return 0
        return int(rows[0].get("count", 0))


def _parse_count(body: str) -> int:
    # PostgREST returns the scalar as bare JSON (e.g. "3" or "3\n").
    return int(body.strip())


def STORAGE(url: str, anon_key: str) -> SupabaseStorage:
    """Factory called by the host. Signature widens in #28 (manifest deps)."""
    return SupabaseStorage(url=url, anon_key=anon_key)
