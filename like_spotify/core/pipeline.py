import logging
from collections.abc import Callable, Sequence

from .actions import PostLikeAction, PreLikeAction
from .music_provider import MusicProvider
from .storage import Storage
from .types import CurrentTrack, LikeContext

FeedbackFn = Callable[[bool, str, str], None]

logger = logging.getLogger(__name__)


class Pipeline:
    """Composes a MusicProvider + optional Storage + action chains.

    Order of operations in `run_once`:
        1. get_currently_playing
        2. PreLikeAction chain — any action returning False aborts the like
        3. is_liked probe (only when Storage is wired — feeds the backfill flag)
        4. MusicProvider.like
        5. Storage.increment (soft-fail; new count shown in feedback title)
        6. PostLikeAction chain — each action runs independently, failures
           are logged and the chain continues

    Slice history:
        #21 — tracer-bullet (1, 4, feedback)
        #22 — Storage wiring (5)
        #23 — Pre/PostLikeAction chains (2, 6)
        #24 — backfill probe (3): first encounter of an already-liked track
              counts as 2; the flag is gated on Storage presence so we don't
              spend an extra Spotify call when no counter is configured.
    """

    def __init__(
        self,
        provider: MusicProvider,
        feedback: FeedbackFn,
        storage: Storage | None = None,
        pre_like_actions: Sequence[PreLikeAction] = (),
        post_like_actions: Sequence[PostLikeAction] = (),
    ) -> None:
        self._provider = provider
        self._feedback = feedback
        self._storage = storage
        self._pre_actions = tuple(pre_like_actions)
        self._post_actions = tuple(post_like_actions)

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

        # ── Pre-like chain ────────────────────────────────────────────────
        for action in self._pre_actions:
            try:
                proceed = await action.run(ctx)
            except Exception as e:
                # An action's internal failure does NOT abort the like —
                # the contract is "actions are independent". Log + continue.
                logger.warning(
                    "PreLikeAction %s raised: %s", type(action).__name__, e
                )
                continue
            if not proceed:
                self._feedback(
                    False,
                    f"Skipped by {type(action).__name__}",
                    _display(ctx.track),
                )
                return

        # ── Backfill probe (#24): only when Storage is wired. ─────────────
        # Soft fail to False — better to miss a +1 backfill than double-count.
        was_already_liked = False
        if self._storage is not None:
            try:
                was_already_liked = await self._provider.is_liked(ctx.track)
            except Exception:
                was_already_liked = False

        # ── Like ──────────────────────────────────────────────────────────
        try:
            await self._provider.like(ctx.track)
        except Exception as e:
            self._feedback(False, "Like failed", str(e))
            return

        # ── Storage (#22, soft fail) ──────────────────────────────────────
        if self._storage is not None:
            try:
                user_id = await self._provider.user_id()
                ctx.like_count = await self._storage.increment(
                    user_id, ctx.track, was_already_liked
                )
            except Exception:
                ctx.like_count = None

        # ── Post-like chain (independent, log + continue on failure) ──────
        for action in self._post_actions:
            try:
                await action.run(ctx)
            except Exception as e:
                logger.warning(
                    "PostLikeAction %s raised: %s", type(action).__name__, e
                )

        title = "Liked" if ctx.like_count is None else f"Liked × {ctx.like_count}"
        self._feedback(True, title, _display(ctx.track))


def _display(track: CurrentTrack) -> str:
    artists = ", ".join(track.artists) if track.artists else ""
    return f"{track.title} — {artists}" if artists else track.title
