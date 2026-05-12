from abc import ABC, abstractmethod

from .types import CurrentTrack


class Storage(ABC):
    """Persistence for per-track like counters.

    Default impl is `SupabaseStorage` (cross-device counter); a future
    `GoogleSheetsStorage` (#25) validates the abstraction with a second
    backend. Failure is non-fatal — the like must succeed even if the
    storage is misconfigured or unreachable; the host treats `None` as
    'counter silently unavailable'.

    Track identity is delegated to the impl: most will key on
    `track.provider_track_id`, but a sheet-style impl may want
    title/artist for human-readable rows.
    """

    @abstractmethod
    async def increment(self, user_id: str, track: CurrentTrack) -> int:
        """Atomically bump the like counter for (user, track). Returns new count."""

    @abstractmethod
    async def get_count(self, user_id: str, track: CurrentTrack) -> int:
        """Current count for (user, track). 0 if never liked."""
