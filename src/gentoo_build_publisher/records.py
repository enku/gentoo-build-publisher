"""DB interface for Gentoo Build Publisher"""
from __future__ import annotations

import importlib.metadata
from typing import Type

from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.types import RecordDB


class Records:  # pylint: disable=too-few-public-methods
    """Just a wrapper to look like storage and jenkins modules"""

    @staticmethod
    def from_settings(settings: Settings) -> RecordDB:
        """Return instance of the the RecordDB class given in settings"""
        try:
            [backend] = importlib.metadata.entry_points(
                group="gentoo_build_publisher.records", name=settings.RECORDS_BACKEND
            )
        except ValueError:
            raise LookupError(
                f"RECORDS_BACKEND not found: {settings.RECORDS_BACKEND}"
            ) from None

        record_db: Type[RecordDB] = backend.load()

        return record_db()
