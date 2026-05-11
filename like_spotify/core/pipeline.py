from collections.abc import Callable

from .music_provider import MusicProvider
from .types import CurrentTrack, LikeContext

FeedbackFn = Callable[[bool, str, str], None]


class Pipeline:
    """Composes a MusicProvider with feedback hooks.

    Tracer bullet scope (#21): currently_playing -> like -> feedback.
    PreLikeActions / Storage / PostLikeActions plug in here in #22 / #23.
    """

    def __init__(self, provider: MusicProvider, feedback: FeedbackFn) -> None:
        self._provider = provider
        self._feedback = feedback

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

        self._feedback(True, "Liked", _display(ctx.track))


def _display(track: CurrentTrack) -> str:
    artists = ", ".join(track.artists) if track.artists else ""
    return f"{track.title} — {artists}" if artists else track.title
