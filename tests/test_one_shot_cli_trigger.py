"""Contract tests for OneShotCliTrigger.

Slice: #27 (second Trigger impl validating the interface).
"""

from __future__ import annotations

import pytest

from like_spotify.core.trigger import Trigger
from like_spotify.extensions.one_shot_cli_trigger import (
    TRIGGER,
    OneShotCliTrigger,
)


@pytest.mark.asyncio
async def test_emits_exactly_once_on_start() -> None:
    trigger = OneShotCliTrigger()
    calls = 0

    async def emit() -> None:
        nonlocal calls
        calls += 1

    await trigger.start(emit)
    await trigger.stop()

    assert calls == 1


@pytest.mark.asyncio
async def test_start_is_idempotent() -> None:
    """Re-entering start() must not double-emit."""
    trigger = OneShotCliTrigger()
    calls = 0

    async def emit() -> None:
        nonlocal calls
        calls += 1

    await trigger.start(emit)
    await trigger.start(emit)

    assert calls == 1


@pytest.mark.asyncio
async def test_stop_is_idempotent() -> None:
    trigger = OneShotCliTrigger()

    async def emit() -> None:
        pass

    await trigger.start(emit)
    await trigger.stop()
    await trigger.stop()  # must not raise


@pytest.mark.asyncio
async def test_start_after_stop_does_not_emit() -> None:
    trigger = OneShotCliTrigger()
    calls = 0

    async def emit() -> None:
        nonlocal calls
        calls += 1

    await trigger.stop()
    await trigger.start(emit)

    assert calls == 0


@pytest.mark.asyncio
async def test_emit_exception_propagates() -> None:
    """Errors inside emit are the host's problem — Trigger does not swallow.

    The tray trigger also lets exceptions surface (via the run_coroutine
    future); same contract here so a CLI host can exit non-zero.
    """
    trigger = OneShotCliTrigger()

    async def emit() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await trigger.start(emit)


def test_factory_returns_trigger_instance() -> None:
    assert isinstance(TRIGGER(), Trigger)
    assert isinstance(TRIGGER(), OneShotCliTrigger)
