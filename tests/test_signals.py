"""Tests for Gentoo Build Publisher signals"""

# pylint: disable=missing-docstring
from typing import Any
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
        with self.assertRaises(signals.DoesNotExistError) as context:
            dispatcher.bind(bogus=lambda: None)

        exception = context.exception
        self.assertEqual(str(exception), 'Event "bogus" not registered')


class RegisterTests(TestCase):
    def test_can_register(self) -> None:
        dispatcher.register_event("test_event")
        dispatcher.emit("test_event")

        # There doesn't appear to be an "unregister"

        with self.assertRaises(signals.EventExistsError) as context:
            dispatcher.register_event("test_event")

        exception = context.exception
        self.assertEqual(str(exception), '"test_event" already exists')


class PyDispatcherAdapterTests(TestCase):
    # pylint: disable=protected-access
    def test_register_event(self) -> None:
        d = signals.PublisherDispatcher()

        d.register_event("test_event1", "test_event2")

        self.assertIn("test_event1", d._registry)
        self.assertIn("test_event2", d._registry)

    def test_register_same_event(self) -> None:
        d = signals.PublisherDispatcher()

        d.register_event("test_event")

        with self.assertRaises(signals.EventExistsError):
            d.register_event("test_event")

    def test_built_in_signals(self) -> None:
        class MyDispatcher(signals.PublisherDispatcher):
            _events_ = ["this", "that", "the", "other"]

        d = MyDispatcher()

        for event in MyDispatcher._events_:
            self.assertIn(event, d._registry)

    def test_bind_and_emit(self) -> None:
        called = False
        d = signals.PublisherDispatcher()
        d.register_event("test_event")

        def handler(**kwargs: Any) -> None:
            nonlocal called
            self.assertEqual(kwargs, {"this": "that", "the": "other"})
            called = True

        d.bind(test_event=handler)
        d.emit("test_event", this="that", the="other")

        self.assertTrue(called)

    def test_emit_unbound(self) -> None:
        d = signals.PublisherDispatcher()

        with self.assertRaises(signals.DoesNotExistError) as context:
            d.emit("test_event", this="that", the="other")

        exception = context.exception
        self.assertEqual(str(exception), 'Event "test_event" not registered')

    def test_same_handler_multiple_events(self) -> None:
        handled_event1 = False
        handled_event2 = False
        d = signals.PublisherDispatcher()

        d.register_event("event1", "event2")

        def handler(event: str) -> None:
            nonlocal handled_event1, handled_event2

            if event == "event1":
                handled_event1 = True
            if event == "event2":
                handled_event2 = True

        d.bind(event1=handler)
        d.bind(event2=handler)

        d.emit("event1", event="event1")
        self.assertTrue(handled_event1)
        self.assertFalse(handled_event2)

        handled_event1 = False
        d.emit("event2", event="event2")
        self.assertFalse(handled_event1)
        self.assertTrue(handled_event2)

    def test_unbind(self) -> None:
        called = False
        d = signals.PublisherDispatcher()
        d.register_event("test_event")

        def handler(**kwargs: Any) -> None:
            nonlocal called
            self.assertEqual(kwargs, {"this": "that", "the": "other"})
            called = True

        d.bind(test_event=handler)
        d.emit("test_event", this="that", the="other")
        self.assertTrue(called)

        called = False
        d.unbind(handler)
        d.emit("test_event", this="that", the="other")
        self.assertFalse(called)

    def test_unbind_same_handler_multiple_events(self) -> None:
        handled_event1 = False
        handled_event2 = False
        d = signals.PublisherDispatcher()

        d.register_event("event1", "event2")

        def handler(event: str) -> None:
            nonlocal handled_event1, handled_event2

            if event == "event1":
                handled_event1 = True
            if event == "event2":
                handled_event2 = True

        d.bind(event1=handler)
        d.bind(event2=handler)

        d.emit("event1", event="event1")
        d.emit("event2", event="event2")
        self.assertTrue(handled_event1)
        self.assertTrue(handled_event2)

        d.unbind(handler)
        handled_event1 = False
        handled_event2 = False

        d.emit("event1", event="event1")
        d.emit("event2", event="event2")
        self.assertFalse(handled_event1)
        self.assertFalse(handled_event2)

    def test_unbind_not_registered(self) -> None:
        d = signals.PublisherDispatcher()

        def handler(**kwargs: Any) -> None: ...

        with self.assertRaises(signals.NotBoundError) as context:
            d.unbind(handler)

        exception = context.exception
        self.assertEqual(str(exception), '"handler" is not bound to an event')

    def test_get_dispatcher_event(self) -> None:
        d = signals.PublisherDispatcher()
        d.register_event("test_event")

        signal = d.get_dispatcher_event("test_event")

        self.assertEqual(signal.name, "test_event")  # type: ignore[attr-defined]

    def test_get_dispatcher_event_with_unregistered_event(self) -> None:
        d = signals.PublisherDispatcher()

        with self.assertRaises(signals.DoesNotExistError):
            d.get_dispatcher_event("bogus")
