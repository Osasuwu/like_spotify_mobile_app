"""Storage contract suite — parametrized across every shipped impl.

Each impl is wired to an in-memory simulator over `requests`; the tests
themselves only see the `Storage` ABC and assert the invariants that
the abstraction promises:

    - increment N times → count goes 1, 2, 3, … N
    - first encounter with `was_already_liked=True` → count 2
    - subsequent presses with True still in effect → +1 each, NOT +2
      (backfill is idempotent — flag only matters on INSERT)
    - increment with False then True → count goes 1, then 2 (the flag is
      ignored after first encounter)
    - get_count for a never-touched key → 0
    - get_count for an existing key → current count

A regression on either impl that breaks the contract surfaces here
*before* the impl-specific HTTP-shape tests catch it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from like_spotify.core.storage import Storage
from like_spotify.core.types import CurrentTrack
from like_spotify.extensions.google_sheets_storage import GoogleSheetsStorage
from like_spotify.extensions.supabase_storage import SupabaseStorage


# ── Fake backends ────────────────────────────────────────────────────────


@dataclass
class FakeResponse:
    status_code: int
    text: str = ""
    json_body: Any = None

    def json(self) -> Any:
        return self.json_body


class SupabaseSim:
    """In-memory mirror of the Supabase RPCs + tables."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}
        self.artist_rows: set[tuple[str, str, str]] = set()

    def handle_post(self, url: str, **kw) -> FakeResponse:
        body = kw.get("json", {})
        if url.endswith("/rpc/increment_track_like"):
            key = (body["p_user_id"], body["p_track_id"])
            flag = bool(body.get("p_was_already_liked", False))
            if key not in self.rows:
                self.rows[key] = {
                    "count": 2 if flag else 1,
                    "backfilled": flag,
                }
            else:
                self.rows[key]["count"] += 1
            return FakeResponse(status_code=200, text=str(self.rows[key]["count"]))
        if url.endswith("/rpc/record_artist_track"):
            triple = (body["p_user_id"], body["p_artist_id"], body["p_track_id"])
            self.artist_rows.add(triple)
            count = sum(
                1
                for u, a, _t in self.artist_rows
                if u == triple[0] and a == triple[1]
            )
            return FakeResponse(status_code=200, text=str(count))
        return FakeResponse(status_code=404, text="unknown rpc")

    def handle_get(self, url: str, **kw) -> FakeResponse:
        params = kw.get("params") or {}
        user = (params.get("user_id") or "").removeprefix("eq.")
        track = (params.get("track_id") or "").removeprefix("eq.")
        row = self.rows.get((user, track))
        return FakeResponse(
            status_code=200,
            json_body=[{"count": row["count"]}] if row else [],
        )


class SheetsSim:
    def __init__(
        self, sheet: str = "Likes", artist_sheet: str = "ArtistTracks"
    ) -> None:
        self.sheets: dict[str, list[list]] = {
            sheet: [["user_id", "track_id", "count", "backfilled", "updated_at"]],
            artist_sheet: [["user_id", "artist_id", "track_id", "created_at"]],
        }
        self.sheet = sheet
        self.artist_sheet = artist_sheet

    def _sheet_for(self, url: str) -> str:
        """Extract sheet name from `.../values/<sheet>` or `.../values/<sheet>:append`."""
        tail = url.rsplit("/values/", 1)[-1]
        sheet = tail.split(":")[0].split("!")[0]
        return sheet

    def handle_get(self, url: str, **kw) -> FakeResponse:
        sheet = self._sheet_for(url)
        rows = self.sheets.get(sheet)
        if rows is None:
            return FakeResponse(status_code=400, text=f"unknown sheet {sheet}")
        return FakeResponse(status_code=200, json_body={"values": list(rows)})

    def handle_post(self, url: str, **kw) -> FakeResponse:
        body = kw.get("json", {})
        sheet = self._sheet_for(url)
        rows = self.sheets.setdefault(sheet, [])
        for row in body.get("values", []):
            rows.append(list(row))
        row_index = len(rows)
        return FakeResponse(
            status_code=200,
            json_body={"updates": {"updatedRange": f"{sheet}!A{row_index}:E{row_index}"}},
        )

    def handle_put(self, url: str, **kw) -> FakeResponse:
        tail = url.rsplit("/values/", 1)[-1]
        sheet, _, a1 = tail.partition("!")
        rows = self.sheets[sheet]
        col_letter = a1.split(":")[0].rstrip("0123456789")
        row_digits = a1.split(":")[0][len(col_letter):]
        row_idx = int(row_digits)
        col = ord(col_letter.upper()) - ord("A")
        new_value = kw["json"]["values"][0][0]
        while len(rows[row_idx - 1]) <= col:
            rows[row_idx - 1].append("")
        rows[row_idx - 1][col] = new_value
        return FakeResponse(status_code=200, json_body={})


# ── Fixtures: each impl wired to its sim ─────────────────────────────────


@pytest.fixture
def supabase_storage(monkeypatch) -> Storage:
    sim = SupabaseSim()
    monkeypatch.setattr(
        "like_spotify.extensions.supabase_storage.requests.post", sim.handle_post
    )
    monkeypatch.setattr(
        "like_spotify.extensions.supabase_storage.requests.get", sim.handle_get
    )
    return SupabaseStorage(url="https://x.supabase.co", anon_key="k")


@pytest.fixture
def sheets_storage(monkeypatch) -> Storage:
    sim = SheetsSim()
    monkeypatch.setattr(
        "like_spotify.extensions.google_sheets_storage.requests.get", sim.handle_get
    )
    monkeypatch.setattr(
        "like_spotify.extensions.google_sheets_storage.requests.post", sim.handle_post
    )
    monkeypatch.setattr(
        "like_spotify.extensions.google_sheets_storage.requests.put", sim.handle_put
    )
    return GoogleSheetsStorage(
        spreadsheet_id="s", token_provider=lambda: "tok"
    )


# Parametrize every contract test across both fixtures. Using indirect
# fixture references keeps the test functions readable.
@pytest.fixture(params=["supabase_storage", "sheets_storage"])
def storage(request) -> Storage:
    return request.getfixturevalue(request.param)


def _track(track_id: str = "abc") -> CurrentTrack:
    return CurrentTrack(
        provider="spotify", provider_track_id=track_id, title="t", artists=("a",)
    )


# ── Contract invariants ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_increment_returns_running_count(storage: Storage) -> None:
    c1 = await storage.increment("user-1", _track("trk-a"))
    c2 = await storage.increment("user-1", _track("trk-a"))
    c3 = await storage.increment("user-1", _track("trk-a"))
    assert (c1, c2, c3) == (1, 2, 3)


@pytest.mark.asyncio
async def test_first_encounter_was_already_liked_returns_two(
    storage: Storage,
) -> None:
    count = await storage.increment(
        "user-1", _track("trk-a"), was_already_liked=True
    )
    assert count == 2


@pytest.mark.asyncio
async def test_subsequent_was_already_liked_still_plus_one(
    storage: Storage,
) -> None:
    """Flag is honoured ONCE on INSERT; later presses are plain +1."""
    a = await storage.increment("user-1", _track("trk-a"), was_already_liked=True)
    b = await storage.increment("user-1", _track("trk-a"), was_already_liked=True)
    c = await storage.increment("user-1", _track("trk-a"), was_already_liked=True)
    assert (a, b, c) == (2, 3, 4)


@pytest.mark.asyncio
async def test_flag_ignored_after_first_encounter_without_it(
    storage: Storage,
) -> None:
    """If first press was False, a later True doesn't retroactively backfill."""
    a = await storage.increment("user-1", _track("trk-a"), was_already_liked=False)
    b = await storage.increment("user-1", _track("trk-a"), was_already_liked=True)
    assert (a, b) == (1, 2)


@pytest.mark.asyncio
async def test_get_count_zero_for_unknown_key(storage: Storage) -> None:
    assert await storage.get_count("user-1", _track("never")) == 0


@pytest.mark.asyncio
async def test_get_count_reflects_running_total(storage: Storage) -> None:
    await storage.increment("user-1", _track("trk-a"))
    await storage.increment("user-1", _track("trk-a"))
    assert await storage.get_count("user-1", _track("trk-a")) == 2


@pytest.mark.asyncio
async def test_record_artist_track_returns_distinct_count(storage: Storage) -> None:
    a = await storage.record_artist_track("u1", "art1", "trk-a")
    b = await storage.record_artist_track("u1", "art1", "trk-b")
    c = await storage.record_artist_track("u1", "art1", "trk-c")
    assert (a, b, c) == (1, 2, 3)


@pytest.mark.asyncio
async def test_record_artist_track_is_idempotent(storage: Storage) -> None:
    """Re-recording the same triple does NOT increment."""
    first = await storage.record_artist_track("u1", "art1", "trk-a")
    second = await storage.record_artist_track("u1", "art1", "trk-a")
    third = await storage.record_artist_track("u1", "art1", "trk-a")
    assert (first, second, third) == (1, 1, 1)


@pytest.mark.asyncio
async def test_record_artist_track_separates_artists(storage: Storage) -> None:
    await storage.record_artist_track("u1", "art1", "trk-a")
    await storage.record_artist_track("u1", "art1", "trk-b")
    other = await storage.record_artist_track("u1", "art2", "trk-a")
    assert other == 1  # different artist starts at 1


@pytest.mark.asyncio
async def test_keys_are_independent(storage: Storage) -> None:
    """Different (user, track) tuples don't bleed into each other."""
    await storage.increment("user-1", _track("trk-a"))
    await storage.increment("user-1", _track("trk-a"))
    await storage.increment("user-2", _track("trk-a"))
    await storage.increment("user-1", _track("trk-b"))

    assert await storage.get_count("user-1", _track("trk-a")) == 2
    assert await storage.get_count("user-2", _track("trk-a")) == 1
    assert await storage.get_count("user-1", _track("trk-b")) == 1
