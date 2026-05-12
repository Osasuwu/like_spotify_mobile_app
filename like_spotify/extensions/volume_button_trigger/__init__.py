"""VolumeButtonTrigger — skeleton.

Emit a like intent on a vol-up-up double-tap on a connected HID
device. Watches an HID volume-up event stream; two presses inside
`DOUBLE_TAP_WINDOW_MS` count as a like signal. Single presses still
adjust system volume normally — we don't suppress them.

**Status: skeleton.** The HID discovery + read loop are TODOs.
See CONTRIBUTING.md → "Skeleton for a third trigger" for the
end-to-end pick-up checklist. Manifest stage is `experimental`.

Pattern-matching shape mirrors the Android
`MediaEventPatternDetector.kt` — same domain, different language.

Slice: #29 (skeleton drop, no impl).
"""

from __future__ import annotations

import asyncio
import time

from like_spotify.core.trigger import EmitFn, Trigger

DOUBLE_TAP_WINDOW_MS = 400


class VolumeButtonTrigger(Trigger):
    """Match two vol-up presses inside `double_tap_window_ms` → emit.

    The double-tap matcher is fully implemented and unit-testable in
    isolation — it's just a stamp comparator. The missing piece is
    `_listen`, which must read an HID device and call
    `_on_volume_up()` per event.
    """

    def __init__(self, double_tap_window_ms: int = DOUBLE_TAP_WINDOW_MS) -> None:
        self._window_ms = double_tap_window_ms
        self._last_press_ms: float | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._emit: EmitFn | None = None
        self._task: asyncio.Task | None = None

    async def start(self, emit: EmitFn) -> None:
        self._loop = asyncio.get_running_loop()
        self._emit = emit
        self._task = self._loop.create_task(self._listen())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        # TODO: close the HID device handle here.

    async def _listen(self) -> None:
        """HID read loop. TODO — see module docstring.

        Pick this up by:

          1. Decide your HID library (hidapi via `pip install hid`,
             or evdev on Linux). Add it to manifest.requirements.
          2. Open the volume-keys device (you'll need to enumerate
             and filter; on Windows it's a HID consumer-control
             device, on Linux it's an evdev `KEY_VOLUMEUP` keysym).
          3. On each volume-up event, call `self._on_volume_up()`.
             Do NOT suppress the event — single presses still adjust
             system volume.
        """
        raise NotImplementedError(
            "VolumeButtonTrigger HID listener — see CONTRIBUTING.md"
        )

    def _on_volume_up(self, now_ms: float | None = None) -> None:
        """Pure pattern matcher. Side-effect-free except for emit."""
        now_ms = now_ms if now_ms is not None else time.monotonic() * 1000
        if (
            self._last_press_ms is not None
            and (now_ms - self._last_press_ms) <= self._window_ms
        ):
            # Double-tap matched — reset so a third press doesn't also fire.
            self._last_press_ms = None
            if self._loop is not None and self._emit is not None:
                asyncio.run_coroutine_threadsafe(self._emit(), self._loop)
            return
        self._last_press_ms = now_ms


def TRIGGER(double_tap_window_ms: int = DOUBLE_TAP_WINDOW_MS) -> VolumeButtonTrigger:
    return VolumeButtonTrigger(double_tap_window_ms=double_tap_window_ms)
