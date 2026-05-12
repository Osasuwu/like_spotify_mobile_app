from collections.abc import Callable

from .music_provider import MusicProvider
from .storage import Storage
from .types import CurrentTrack, LikeContext

FeedbackFn = Callable[[bool, str, str], None]


class Pipeline:
    """Composes a MusicProvider + optional Storage with feedback hooks.

    Tracer bullet (#21): currently_playing -> like -> feedback.
    #22 adds Storage: after a successful like, increment a per-(user, track)
    counter; surface the new count in feedback. Storage failure must NOT
    fail the like — it's a soft signal, the host shows "Liked" without a
    count. PreLikeActions / PostLikeActions plug in here in #23.
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
        try:
            await self._provider.like(ctx.track)
        except Exception as e:
            self._feedback(False, "Like failed", str(e))
            return

        if self._storage is not None:
            try:
                user_id = await self._provider.user_id()
                ctx.like_count = await self._storage.increment(user_id, ctx.track)
            except Exception:
                # Soft fail: counter unavailable, like still succeeded.
                ctx.like_count = None

        title = "Liked" if ctx.like_count is None else f"Liked × {ctx.like_count}"
        self._feedback(True, title, _display(ctx.track))


def _display(track: CurrentTrack) -> str:
    artists = ", ".join(track.artists) if track.artists else ""
    return f"{track.title} — {artists}" if artists else track.title
