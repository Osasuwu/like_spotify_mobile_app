from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from .types import CurrentTrack


class MusicProvider(ABC):
    """Read 'what is playing' and write 'I like this'. Nothing else.

    Stays narrow on purpose. Charts, history, social — out of scope;
    if a future need arises, it's a new extension point, not a method here.
    """

    @abstractmethod
    async def get_currently_playing(self) -> CurrentTrack | None: ...

    @abstractmethod
    async def like(self, track: CurrentTrack) -> None: ...

    @abstractmethod
    async def is_liked(self, track: CurrentTrack) -> bool:
        """True iff the user already had this track in their liked collection.

        Read before `like()` to power the #24 backfill: first encounter of
        a pre-existing like counts as 2. Cheap O(1) lookup is expected.
        """

    @abstractmethod
    async def user_id(self) -> str:
        """Stable per-user id. Storage keys against it.

        Expected O(1) after setup (cached post-auth value). Async because
        a future provider may need a lazy fetch on first call.
        """


@runtime_checkable
class PlaylistCapableProvider(Protocol):
    """Optional capability: named-playlist read/write + follow-artist.

    Spotify-flavored extras that don't belong on the base `MusicProvider`
    (per docs/design/interfaces.md §4.6 — stay at one flag until >=3 real
    capability axes emerge; this is that first axis). Call sites that need
    them check `isinstance(provider, PlaylistCapableProvider)` instead of
    duplicating an `isinstance(provider, SpotifyMusicProvider)` or
    `getattr(provider, "...", None)` probe each — `SpotifyMusicProvider`
    satisfies this structurally, no inheritance required.
    """

    async def find_playlist_by_name(self, name: str) -> str | None: ...

    async def get_playlist_track_ids(self, playlist_id: str) -> set[str]: ...

    async def remove_track_from_playlist(
        self, track_id: str, playlist_id: str
    ) -> None: ...

    async def follow_artist(self, artist_id: str) -> None: ...
