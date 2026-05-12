from abc import ABC, abstractmethod

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
