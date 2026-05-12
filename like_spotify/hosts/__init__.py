"""hosts — runtime shells that wire a Trigger + MusicProvider + feedback.

Phase 1 (#21) shipped the default Windows tray host. Issue #27 split the
seam: `windows.py` owns the resident tray + global hotkey + autostart;
`_stub.py` is the macOS/Linux CLI fallback. The right one is chosen at
startup based on `sys.platform`.

Real `hosts/macos.py` / `hosts/linux.py` (full tray + native autostart)
are flagged in CONTRIBUTING.md as good-first-PR.
"""

from __future__ import annotations

import sys
from collections.abc import Callable


def select_host() -> Callable[[list[str] | None], int]:
    """Return the platform-appropriate host's `main(argv)` callable."""
    if sys.platform == "win32":
        from . import windows

        return windows.main
    from . import _stub

    return _stub.main


def main(argv: list[str] | None = None) -> int:
    return select_host()(argv)
