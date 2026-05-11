"""extensions — default-flavor implementations of the five core seams.

Filesystem-convention plugin layout (Music Assistant-style): each subdir
is one extension keyed by `domain`, with `__init__.py` exporting one of
TRIGGER / PRE_LIKE_ACTION / MUSIC_PROVIDER / POST_LIKE_ACTION / STORAGE,
plus a `manifest.json` describing metadata + pip requirements.

Phase 1 tracer (#21) ships two: `spotify` (MusicProvider) and
`tray_hotkey_trigger` (Trigger).
"""
