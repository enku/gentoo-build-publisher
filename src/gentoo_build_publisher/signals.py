"""Signal dispatcher for Gentoo Build Publisher"""

from pydispatch import Dispatcher


class PublisherDispatcher(Dispatcher):
    """GBP event dispatcher"""

    _events_ = ["predelete", "postdelete", "published", "prepull", "postpull"]


dispatcher = PublisherDispatcher()
