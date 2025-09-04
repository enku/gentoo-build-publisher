"""Signal dispatcher for Gentoo Build Publisher"""

from pydispatch import Dispatcher, DoesNotExistError, EventExistsError

CORE_EVENTS = ["predelete", "postdelete", "published", "prepull", "postpull"]


class PublisherDispatcher(Dispatcher):
    """GBP event dispatcher"""

    _events_ = CORE_EVENTS


dispatcher = PublisherDispatcher()


__all__ = ("dispatcher", "DoesNotExistError", "EventExistsError")
