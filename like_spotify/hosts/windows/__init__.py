"""Windows host — tray + global hotkey, the default flavor.

Owns the Win32 side effects: tray icon, single-instance mutex, balloon
notifications, synthesized-tone beep feedback, and the `HKCU\\…\\Run`
autostart toggle. Anything cross-platform lives in `hosts/_common.py` so
the `_stub.py` host (mac/linux CLI) can share it.

This module is the thin composition point; the concerns themselves live in:
    feedback.py  — tray icon bitmaps + synthesized-tone beep (`TrayFeedback`)
    autostart.py — `HKCU\\…\\Run` registry toggle + venv-bypass VBScript launch
    tray.py      — pystray Icon/Menu construction for the resident host
    resident.py  — single-instance mutex, one-shot subcommands, startup
                   logging/shell-wait, `_run_resident_host`, `main`

`_autostart_enabled`/`_autostart_set` are re-exported because
`hosts/_common.py`'s setup wizard reaches into them directly
(`from like_spotify.hosts import windows as _win`).

Slice history:
    #21 — original tray launcher.
    #27 — renamed from `hosts/tray.py`; cross-platform helpers and the
          `like-once` subcommand split out so the same entry point works
          on every OS.
    #53 — swapped `MessageBeep` for a synthesized tone played via
          `PlaySound(..., SND_MEMORY)` (see `feedback._synth_tone`).
    #55 — split this god-module into the package above.
"""

from __future__ import annotations

from .autostart import _autostart_enabled, _autostart_set
from . import resident


def main(argv: list[str] | None = None) -> int:
    return resident.main(argv)


__all__ = ["main", "_autostart_enabled", "_autostart_set"]
