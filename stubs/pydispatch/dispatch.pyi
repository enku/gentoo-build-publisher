import typing as t


class Dispatcher:
    def bind(self, **kwargs: t.Callable[..., None]) -> None: ...
    def unbind(self, *args: t.Callable[..., None]) -> None: ...
    def emit(self, name: str, *args: t.Any, **kwargs: t.Any) -> t.Any: ...
    def register_event(self, *names: str) -> None: ...


class DoesNotExistError(Exception):
    pass

class EventExistsError(Exception):
    pass
