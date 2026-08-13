"""Windows host — tray icon rendering + synthesized-tone beep feedback.

Split out of `hosts/windows.py` in #55. Owns everything `TrayFeedback`
needs to confirm a like/remove/error to the user: the heart icon bitmaps
and the PCM tone synthesis played through `winsound.PlaySound`.
"""

from __future__ import annotations

import math
import struct
import threading
import time
from array import array

from .. import _common

# ── Tray icon + feedback ───────────────────────────────────────────────


def _make_heart_icon(color: tuple[int, int, int]):
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size
    d.ellipse([s * 0.05, s * 0.10, s * 0.52, s * 0.57], fill=color)
    d.ellipse([s * 0.48, s * 0.10, s * 0.95, s * 0.57], fill=color)
    d.polygon(
        [(s * 0.02, s * 0.38), (s * 0.50, s * 0.95), (s * 0.98, s * 0.38)],
        fill=color,
    )
    return img


_ICON_GREEN = (30, 215, 96)
_ICON_WHITE = (255, 255, 255)
_ICON_RED = (255, 60, 60)


_TONE_SAMPLE_RATE = 44100


def _synth_tone(segments: list[tuple[int, int]], volume: float = 1.0) -> bytes:
    """Render (frequency_hz, duration_ms) segments to an in-memory PCM16
    mono WAV buffer, playable via `winsound.PlaySound(..., SND_MEMORY)`.

    Exists because the two built-in `winsound` options both failed on
    real hardware: `MessageBeep` plays a named system-event sound, which
    Focus Assist / Do Not Disturb suppresses like any notification sound;
    `Beep` drives the legacy PC-speaker/timer tone, which modern audio
    codecs leave unwired to the physical speakers (confirmed silent here —
    only a brief hiccup in whatever else was playing). A synthesized tone
    plays as an ordinary audio-session buffer instead, mirroring the
    phone's `ToneGenerator(AudioManager.STREAM_MUSIC, ...)` feedback
    (`FeedbackPlayer.kt`) rather than routing through any OS notification
    channel.

    `volume` (0.0-1.0, see `_common.resolve_feedback_volume`) scales a
    24000-peak waveform, so 0.5 reproduces the level this shipped at
    before the setting existed.
    """
    peak = 24000 * max(0.0, min(1.0, volume))
    fade = int(_TONE_SAMPLE_RATE * 0.005)  # 5ms fade in/out — avoids clicks
    gap = int(_TONE_SAMPLE_RATE * 0.03)  # 30ms silence between notes
    samples = array("h")
    for freq, duration_ms in segments:
        n = int(_TONE_SAMPLE_RATE * duration_ms / 1000)
        for i in range(n):
            amp = 1.0
            if i < fade:
                amp = i / fade
            elif i > n - fade:
                amp = (n - i) / fade
            value = math.sin(2 * math.pi * freq * i / _TONE_SAMPLE_RATE)
            samples.append(int(value * amp * peak))
        samples.extend([0] * gap)
    data = samples.tobytes()
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        1,  # mono
        _TONE_SAMPLE_RATE,
        _TONE_SAMPLE_RATE * 2,  # byte rate (16-bit mono)
        2,  # block align
        16,  # bits per sample
        b"data",
        len(data),
    )
    return header + data


def _synth_tones(volume: float) -> dict[str, bytes]:
    """Rising two-note chime (like), a single mid tone (remove), a low
    double buzz (error) — distinct enough to tell apart without looking
    at the tray. Rebuilt per `TrayFeedback` instance so `volume` (from
    `trigger.feedback_volume`) takes effect.
    """
    return {
        "like": _synth_tone([(784, 90), (1175, 110)], volume=volume),
        "remove": _synth_tone([(587, 150)], volume=volume),
        "error": _synth_tone([(220, 90), (220, 90)], volume=volume),
    }


class TrayFeedback:
    """Owns the tray icon + flash / beep / balloon feedback."""

    def __init__(
        self, hotkey: str, volume: float = _common.DEFAULT_FEEDBACK_VOLUME
    ) -> None:
        self._hotkey = hotkey
        self._icon_default = _make_heart_icon(_ICON_GREEN)
        self._icon_success = _make_heart_icon(_ICON_WHITE)
        self._icon_error = _make_heart_icon(_ICON_RED)
        self._icon = None  # set in run()
        self._tones = _synth_tones(volume)

    def attach(self, icon) -> None:
        self._icon = icon

    def __call__(
        self, success: bool, title: str, message: str, *, kind: str = "like"
    ) -> None:
        threading.Thread(
            target=self._beep, args=(success, kind), daemon=True
        ).start()
        threading.Thread(target=self._flash, args=(success,), daemon=True).start()
        if self._icon is not None:
            try:
                self._icon.notify(message or title, "Like Spotify")
            except Exception:
                pass

    def _flash(self, success: bool) -> None:
        if self._icon is None:
            return
        self._icon.icon = self._icon_success if success else self._icon_error
        time.sleep(0.4)
        self._icon.icon = self._icon_default

    def _beep(self, success: bool, kind: str) -> None:
        """Audible confirmation through the default sound device.

        Plays a synthesized tone (`_synth_tone`, see module docstring) via
        `PlaySound(..., SND_MEMORY)` rather than `MessageBeep` or `Beep` —
        both proved unreliable/silent on real hardware. Distinct tones per
        outcome so like / remove / error are distinguishable without
        looking at the tray.
        """
        import winsound

        if not success:
            tone = self._tones["error"]
        elif kind == "remove":
            tone = self._tones["remove"]
        else:
            tone = self._tones["like"]
        winsound.PlaySound(tone, winsound.SND_MEMORY)

    @property
    def default_icon(self):
        return self._icon_default
