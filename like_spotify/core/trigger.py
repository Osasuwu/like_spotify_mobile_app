from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

EmitFn = Callable[[], Awaitable[None]]


class Trigger(ABC):
    """Long-lived source of like intents.

    Host calls `start(emit)` once. The trigger calls `emit()` each time
    the user signals 'like the current track'. `stop()` is called on
    shutdown and must be idempotent.
    """

    @abstractmethod
    async def start(self, emit: EmitFn) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...
