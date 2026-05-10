from dataclasses import dataclass, field


@dataclass(frozen=True)
class CurrentTrack:
    """What a MusicProvider returns when something is playing.

    `provider_track_id` is opaque to the host and only meaningful inside
    the producing provider — IDs do not cross providers.
    """

    provider: str
    provider_track_id: str
    title: str
    artists: tuple[str, ...]
    artist_ids: tuple[str, ...] = ()
    album: str | None = None


@dataclass
class LikeContext:
    """Mutable bag passed down the like pipeline.

    Storage and PostLikeActions land in #22 / #23 — the fields are reserved
    here so the pipeline shape doesn't churn when they arrive.
    """

    track: "CurrentTrack"
    like_count: int | None = None
    music_provider: object | None = None
    extras: dict[str, object] = field(default_factory=dict)
