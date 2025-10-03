"""Signal dispatcher for Gentoo Build Publisher"""

from typing import Any, Callable, Concatenate, ParamSpec, TypeAlias

from blinker import Signal, signal

type PyDispatchHandler = Callable[..., Any]

P = ParamSpec("P")
BlinkerHandler: TypeAlias = Callable[Concatenate[Any, P], Any]

CORE_EVENTS = ["postdelete", "postpull", "predelete", "prepull", "published", "tagged"]


class DoesNotExistError(LookupError):
    """Binding or emitting a nonexistent signal"""

    def __init__(self, name: str):
        self.name = name

    def __str__(self) -> str:
        return f'Event "{self.name}" not registered'


class EventExistsError(Exception):
    """Registering an event that already exists in the registry"""

    def __init__(self, name: str):
        self.name = name

    def __str__(self) -> str:
        return f'"{self.name}" already exists'


class NotBoundError(Exception):
    """Unbinding an event that was not bound to an event"""

    def __init__(self, handler: PyDispatchHandler):
        self.handler = handler

    def __str__(self) -> str:
        return f'"{self.handler.__name__}" is not bound to an event'


class PyDispatcherAdapter:
    """Adapter to run python-dispatcher handlers through blinker"""

    def __init__(self) -> None:
        self._registry: dict[str, Signal] = {}
        self._handlers: dict[PyDispatchHandler, set[BlinkerHandler[Any]]] = {}

        event: str
        for event in getattr(self, "_events_", []):
            self._registry[event] = signal(event)

    def register_event(self, *events: str) -> None:
        """Add the given event(s) to to the event registry"""
        for event in events:
            if event in self._registry:
                raise EventExistsError(event)

            self._registry[event] = signal(event)

    def bind(self, **kwargs: PyDispatchHandler) -> None:
        """Bind the python-dispatcher style handlers to the given signal"""
        for signal_name, callback in kwargs.items():
            try:
                sig = self._registry[signal_name]
            except KeyError as error:
                raise DoesNotExistError(signal_name) from error

            adapted_callback = blinker_adapter(callback)
            self._handlers.setdefault(callback, set()).add(adapted_callback)
            sig.connect(adapted_callback)

    def emit(self, signal_name: str, *args: Any, **kwargs: Any) -> None:
        """Emit the given signal"""
        try:
            sig = self._registry[signal_name]
        except KeyError as error:
            raise DoesNotExistError(signal_name) from error

        sig.send(*args, **kwargs)

    def unbind(self, callback: PyDispatchHandler) -> None:
        """Unbind the given signal handler"""
        # remove the reference
        try:
            self._handlers.pop(callback)
        except KeyError as error:
            raise NotBoundError(callback) from error

    def get_dispatcher_event(self, name: str) -> Signal:
        """Return the given registered event (Signal)

        Raise DoesNotExistError if the given event is not registered.
        """
        try:
            return self._registry[name]
        except KeyError as error:
            raise DoesNotExistError(name) from error


def blinker_adapter(callback: PyDispatchHandler) -> BlinkerHandler:  # type: ignore[type-arg]
    """Covert a python-dispatch style handler to a blinker handler"""

    def adapted_callback(_sender: Any, *_args: Any, **kwargs: Any) -> Any:
        return callback(**kwargs)

    return adapted_callback


class PublisherDispatcher(PyDispatcherAdapter):
    """GBP event dispatcher"""

    _events_ = CORE_EVENTS


dispatcher = PublisherDispatcher()


__all__ = ("dispatcher", "DoesNotExistError", "EventExistsError")
