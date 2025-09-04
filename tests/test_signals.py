"""Tests for Gentoo Build Publisher signals"""

# pylint: disable=missing-docstring
from unittest import TestCase

from unittest_fixtures import Fixtures, params

from gentoo_build_publisher import signals
from gentoo_build_publisher.types import Build

BUILD = Build(machine="babette", build_id="test")
dispatcher = signals.dispatcher


@params(event=signals.CORE_EVENTS)
class DispatcherTests(TestCase):
    def test_registers_core_events(self, fixtures: Fixtures) -> None:
        event = fixtures.event

        dispatcher.get_dispatcher_event(event)


class BindNotExistsTest(TestCase):
    def test(self) -> None:
        with self.assertRaises(signals.DoesNotExistError):
            dispatcher.bind(bogus=lambda: None)


class RegisterTests(TestCase):
    def test_can_register(self) -> None:
        dispatcher.register_event("test_event")
        dispatcher.emit("test_event")

        # There doesn't appear to be an "unregister"

        with self.assertRaises(signals.EventExistsError):
            dispatcher.register_event("test_event")
