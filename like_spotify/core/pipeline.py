from collections.abc import Callable

from .music_provider import MusicProvider
from .storage import Storage
from .types import CurrentTrack, LikeContext

FeedbackFn = Callable[[bool, str, str], None]


class Pipeline:
    """Composes a MusicProvider + optional Storage with feedback hooks.

    Tracer bullet (#21): currently_playing -> like -> feedback.
    #22 added Storage: after a successful like, increment a per-(user, track)
    counter; surface the new count in feedback. Storage failure must NOT
    fail the like — soft signal, host shows "Liked" without a count.
    #24 added backfill: when Storage is wired, peek at the provider's
    `is_liked` *before* writing the like, then pass the flag to
    `Storage.increment`. The backend treats first-encounter of an
    already-liked track as count=2 (idempotent — flag only matters on
    the INSERT).
    PreLikeActions / PostLikeActions plug in here in #23.
    """

    def __init__(
        self,
        provider: MusicProvider,
        feedback: FeedbackFn,
        storage: Storage | None = None,
    ) -> None:
        self._provider = provider
        self._feedback = feedback
        self._storage = storage

    async def run_once(self) -> None:
        try:
            track = await self._provider.get_currently_playing()
        except Exception as e:
            self._feedback(False, "Error", f"Could not read playback: {e}")
            return

        if track is None:
            self._feedback(False, "Nothing playing", "")
            return

        ctx = LikeContext(track=track, music_provider=self._provider)

        # Backfill probe: only worth the extra API call when Storage is wired.
        # Soft fail to False — we'd rather miss a +1 backfill than double-count.
        was_already_liked = False
        if self._storage is not None:
            try:
                was_already_liked = await self._provider.is_liked(ctx.track)
            except Exception:
                was_already_liked = False

        try:
            await self._provider.like(ctx.track)
        except Exception as e:
            self._feedback(False, "Like failed", str(e))
            return

        if self._storage is not None:
            try:
                user_id = await self._provider.user_id()
                ctx.like_count = await self._storage.increment(
                    user_id, ctx.track, was_already_liked
                )
            except Exception:
                ctx.like_count = None

        title = "Liked" if ctx.like_count is None else f"Liked × {ctx.like_count}"
        self._feedback(True, title, _display(ctx.track))


def _display(track: CurrentTrack) -> str:
    artists = ", ".join(track.artists) if track.artists else ""
    return f"{track.title} — {artists}" if artists else track.title
