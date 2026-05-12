"""Stub host — macOS / Linux CLI fallback.

Phase 1 ships Windows as the only first-class host. On every other
platform we still want `pip install like-spotify` to be useful, so this
stub host wires up:

    - `--setup` / `--config` (identical to Windows)
    - `like-spotify like-once`  → single like via OneShotCliTrigger

The long-lived `run` command prints a friendly message and exits with a
non-zero code — full tray + global-hotkey support on mac/linux is left
as a good-first-PR (see CONTRIBUTING.md), since `keyboard` needs root on
Linux and `pystray` is awkward outside Win32.

Slice: #27.
"""

from __future__ import annotations

import asyncio
import sys

from like_spotify.core.pipeline import Pipeline
from like_spotify.extensions.one_shot_cli_trigger import (
    TRIGGER as make_one_shot_cli_trigger,
)

from . import _common

_PLATFORM_HINT = {
    "darwin": (
        "Resident tray host is not implemented for macOS yet. Use:\n"
        "    like-spotify like-once\n"
        "to like the currently-playing track. See CONTRIBUTING.md "
        "(`hosts/macos.py`) if you'd like to ship the tray flavor."
    ),
    "linux": (
        "Resident tray host is not implemented for Linux yet. Use:\n"
        "    like-spotify like-once\n"
        "to like the currently-playing track. See CONTRIBUTING.md "
        "(`hosts/linux.py`) if you'd like to ship the tray flavor."
    ),
}


def _no_tray_message() -> str:
    return _PLATFORM_HINT.get(sys.platform, _PLATFORM_HINT["linux"])


class CliFeedback:
    """Plain-stdout feedback for the CLI host."""

    def __init__(self) -> None:
        self.calls: list[tuple[bool, str, str]] = []

    def __call__(self, success: bool, title: str, message: str) -> None:
        self.calls.append((success, title, message))
        stream = sys.stdout if success else sys.stderr
        prefix = "[ok]" if success else "[err]"
        line = f"{prefix} {title}"
        if message:
            line += f" — {message}"
        print(line, file=stream)


def _run_like_once() -> int:
    cfg = _common.load_config()
    client_id = _common.resolve_client_id(cfg)
    if not client_id:
        _common.msgbox(
            "Not configured. Run:\n\n    like-spotify --setup\n",
            title="Like Spotify — setup required",
        )
        return 2

    provider = _common.make_provider(client_id)
    if not provider.has_tokens:
        _common.msgbox(
            "Not authenticated. Run:\n\n    like-spotify --setup\n",
            title="Like Spotify — auth required",
        )
        return 2

    feedback = CliFeedback()
    storage = _common.build_storage(cfg)
    post_actions = _common.build_post_actions(cfg, storage)
    pipeline = Pipeline(
        provider=provider,
        feedback=feedback,
        storage=storage,
        post_like_actions=post_actions,
    )
    trigger = make_one_shot_cli_trigger()

    async def emit() -> None:
        await pipeline.run_once()

    async def run() -> None:
        try:
            await trigger.start(emit)
        finally:
            await trigger.stop()

    asyncio.run(run())

    # Exit code follows the like outcome — useful in scripts.
    if not feedback.calls:
        return 1
    return 0 if feedback.calls[-1][0] else 1


def main(argv: list[str] | None = None) -> int:
    args = _common.parse_args(argv if argv is not None else sys.argv[1:])

    if args.config:
        return _common.print_config_paths()
    if args.setup:
        return _common.do_setup()

    if args.command == "like-once":
        return _run_like_once()

    # Default `run` on a non-tray platform: tell the user what works.
    print(_no_tray_message(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
