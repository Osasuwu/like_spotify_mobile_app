"""Windows host — pystray Icon/Menu construction for the resident tray.

Split out of `hosts/windows.py` in #55. Owns only the menu/icon shape;
the flash/beep/balloon side effects it triggers live in `feedback.py`,
and the click handlers it wires in come from `resident.py` (they close
over the pipeline/event loop, which this module doesn't need to know
about).
"""

from __future__ import annotations

from collections.abc import Callable

from .autostart import _autostart_enabled


def build_icon(
    *,
    feedback,
    hotkey: str,
    remove_enabled: bool,
    remove_hotkey: str | None,
    on_like: Callable,
    on_remove: Callable,
    on_toggle_autostart: Callable,
    on_open_log: Callable,
    on_quit: Callable,
):
    """Build the resident host's pystray.Icon and attach `feedback` to it."""
    import pystray  # local import: heavy

    menu_items: list = [
        pystray.MenuItem(
            f"Like current track  [{hotkey.upper()}]", on_like, default=True
        ),
    ]
    if remove_enabled:
        menu_items.append(
            pystray.MenuItem(
                f"Remove from archive  [{remove_hotkey.upper()}]", on_remove
            )
        )
    menu_items += [
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Start with Windows",
            on_toggle_autostart,
            checked=lambda _item: _autostart_enabled(),
        ),
        pystray.MenuItem("Open log", on_open_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    ]

    icon = pystray.Icon(
        name="LikeSpotify",
        icon=feedback.default_icon,
        title=f"Like Spotify  [{hotkey.upper()}]",
        menu=pystray.Menu(*menu_items),
    )
    feedback.attach(icon)
    return icon
