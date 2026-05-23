"""DD-338 Phase B.1.b — sort-before-return determinism tests.

Covers the 6 multi-record google-home tools that flip
`granularity.deterministic_ordering: unstable → stable` in the catalog:

- ghome_structures, ghome_rooms, ghome_devices  (sort by .name asc)
- ghome_status, ghome_thermostats              (sort by .name asc — DeviceInfo)
- ghome_events                                  (sort newest-first by RFC3339
                                                 timestamp, tie-break on event_id)

Each tool gets an N=5 byte-equal harness using a shuffled-on-each-call mock
fixture, plus targeted sort-key / tie-break / safety tests.
"""

from __future__ import annotations

import random
from unittest.mock import MagicMock, patch

import pytest

from google_home_blade_mcp.server import (
    _event_sort_key,
    ghome_devices,
    ghome_events,
    ghome_rooms,
    ghome_status,
    ghome_structures,
    ghome_thermostats,
)
from tests.conftest import make_camera, make_doorbell, make_room, make_structure, make_thermostat


@pytest.fixture(autouse=True)
def _patch_client(mock_client: MagicMock) -> None:  # type: ignore[type-arg]
    """Patch the client singleton for all determinism tests."""
    with patch("google_home_blade_mcp.server._get_client", return_value=mock_client):
        yield


# ===========================================================================
# Helpers
# ===========================================================================


def _shuffled_factory(items_factory):
    """Return a callable that produces a freshly-shuffled copy of items on each call.

    Used as a side_effect on MagicMock so each invocation sees the upstream
    in deliberately different order, proving the sort wrapper re-canonicalises.
    """

    rng = random.Random(0xDD338)  # seeded for reproducibility

    def _side_effect(*_args, **_kwargs):
        items = list(items_factory())
        rng.shuffle(items)
        return items

    return _side_effect


# ===========================================================================
# N=5 byte-identical determinism harness
# ===========================================================================


class TestDeterministicOrderingStructures:
    """ghome_structures — N=5 invocations must return byte-identical text."""

    async def test_n5_byte_identical(self, mock_client: MagicMock) -> None:
        mock_client.list_structures.side_effect = _shuffled_factory(
            lambda: [
                make_structure("struct-a", "Alpha"),
                make_structure("struct-b", "Bravo"),
                make_structure("struct-c", "Charlie"),
            ]
        )
        outputs = [await ghome_structures() for _ in range(5)]
        assert all(o == outputs[0] for o in outputs), (
            f"Ordering not stable across N=5 invocations. Unique outputs: {len({o for o in outputs})}"
        )


class TestDeterministicOrderingRooms:
    async def test_n5_byte_identical(self, mock_client: MagicMock) -> None:
        mock_client.list_rooms.side_effect = _shuffled_factory(
            lambda: [
                make_room("room-1", "Living Room"),
                make_room("room-2", "Entry"),
                make_room("room-3", "Kitchen"),
                make_room("room-4", "Bedroom"),
            ]
        )
        outputs = [await ghome_rooms(structure_id="struct-1") for _ in range(5)]
        assert all(o == outputs[0] for o in outputs)


class TestDeterministicOrderingDevices:
    async def test_n5_byte_identical_unfiltered(self, mock_client: MagicMock) -> None:
        mock_client.list_devices.side_effect = _shuffled_factory(
            lambda: [
                make_thermostat("thermo-1", "Living Room"),
                make_camera("cam-1", "Front Door Camera"),
                make_doorbell("door-1", "Front Door"),
            ]
        )
        outputs = [await ghome_devices() for _ in range(5)]
        assert all(o == outputs[0] for o in outputs)

    async def test_n5_byte_identical_filtered(self, mock_client: MagicMock) -> None:
        mock_client.list_devices_by_type.side_effect = _shuffled_factory(
            lambda: [
                make_thermostat("thermo-a", "Bedroom"),
                make_thermostat("thermo-b", "Living Room"),
                make_thermostat("thermo-c", "Office"),
            ]
        )
        outputs = [await ghome_devices(device_type="THERMOSTAT") for _ in range(5)]
        assert all(o == outputs[0] for o in outputs)


class TestDeterministicOrderingStatus:
    async def test_n5_byte_identical(self, mock_client: MagicMock) -> None:
        mock_client.list_devices.side_effect = _shuffled_factory(
            lambda: [
                make_thermostat("thermo-1", "Living Room"),
                make_camera("cam-1", "Front Door Camera"),
                make_doorbell("door-1", "Front Door"),
            ]
        )
        outputs = [await ghome_status() for _ in range(5)]
        assert all(o == outputs[0] for o in outputs)


class TestDeterministicOrderingThermostats:
    async def test_n5_byte_identical(self, mock_client: MagicMock) -> None:
        mock_client.list_devices_by_type.side_effect = _shuffled_factory(
            lambda: [
                make_thermostat("thermo-a", "Bedroom"),
                make_thermostat("thermo-b", "Living Room"),
                make_thermostat("thermo-c", "Office"),
            ]
        )
        outputs = [await ghome_thermostats() for _ in range(5)]
        assert all(o == outputs[0] for o in outputs)


class TestDeterministicOrderingEvents:
    async def test_n5_byte_identical(self, mock_client: MagicMock) -> None:
        mock_client.pull_events.side_effect = _shuffled_factory(
            lambda: [
                {"timestamp": "2026-05-23T10:00:00Z", "event_id": "evt-1", "payload": {}},
                {"timestamp": "2026-05-23T11:00:00Z", "event_id": "evt-2", "payload": {}},
                {"timestamp": "2026-05-23T12:00:00Z", "event_id": "evt-3", "payload": {}},
            ]
        )
        outputs = [await ghome_events() for _ in range(5)]
        assert all(o == outputs[0] for o in outputs)


# ===========================================================================
# Sort-key correctness
# ===========================================================================


class TestSortKeyCorrectness:
    """The sort wrapper actually orders by .name (or _event_sort_key) ascending."""

    async def test_structures_sorted_by_name(self, mock_client: MagicMock) -> None:
        mock_client.list_structures.return_value = [
            make_structure("struct-c", "Charlie"),
            make_structure("struct-a", "Alpha"),
            make_structure("struct-b", "Bravo"),
        ]
        result = await ghome_structures()
        # Display names appear in formatter output; ordering on resource name
        # (enterprises/.../structures/struct-{a,b,c}) ⇒ Alpha < Bravo < Charlie.
        a_pos = result.index("Alpha")
        b_pos = result.index("Bravo")
        c_pos = result.index("Charlie")
        assert a_pos < b_pos < c_pos, f"Order wrong: {result}"

    async def test_rooms_sorted_by_name(self, mock_client: MagicMock) -> None:
        mock_client.list_rooms.return_value = [
            make_room("room-c", "Kitchen"),
            make_room("room-a", "Living Room"),
            make_room("room-b", "Entry"),
        ]
        result = await ghome_rooms(structure_id="struct-1")
        # Resource names sort room-a < room-b < room-c ⇒ Living Room < Entry < Kitchen.
        lr_pos = result.index("Living Room")
        en_pos = result.index("Entry")
        kt_pos = result.index("Kitchen")
        assert lr_pos < en_pos < kt_pos


# ===========================================================================
# _event_sort_key direct tests
# ===========================================================================


class TestEventSortKey:
    """Unit tests for the _event_sort_key helper."""

    def test_newest_first(self) -> None:
        events = [
            {"timestamp": "2026-05-23T10:00:00Z", "event_id": "old"},
            {"timestamp": "2026-05-23T12:00:00Z", "event_id": "new"},
            {"timestamp": "2026-05-23T11:00:00Z", "event_id": "mid"},
        ]
        ordered = sorted(events, key=_event_sort_key)
        assert [e["event_id"] for e in ordered] == ["new", "mid", "old"]

    def test_tie_break_by_event_id(self) -> None:
        ts = "2026-05-23T10:00:00Z"
        events = [
            {"timestamp": ts, "event_id": "b"},
            {"timestamp": ts, "event_id": "a"},
            {"timestamp": ts, "event_id": "c"},
        ]
        ordered = sorted(events, key=_event_sort_key)
        # Same epoch ⇒ tie-break on event_id ascending.
        assert [e["event_id"] for e in ordered] == ["a", "b", "c"]

    def test_empty_timestamp_sorts_oldest(self) -> None:
        events = [
            {"timestamp": "", "event_id": "x"},
            {"timestamp": "2026-01-01T00:00:00Z", "event_id": "y"},
        ]
        ordered = sorted(events, key=_event_sort_key)
        # Newest-first: real timestamp first, empty (epoch 0) last.
        assert [e["event_id"] for e in ordered] == ["y", "x"]

    def test_unparseable_timestamp_no_exception(self) -> None:
        events = [
            {"timestamp": "not-a-date", "event_id": "x"},
            {"timestamp": "2026-01-01T00:00:00Z", "event_id": "y"},
        ]
        # Crucially: no exception raised.
        ordered = sorted(events, key=_event_sort_key)
        assert [e["event_id"] for e in ordered] == ["y", "x"]

    def test_missing_event_id_safe(self) -> None:
        events = [
            {"timestamp": "2026-05-23T10:00:00Z"},  # no event_id
            {"timestamp": "2026-05-23T10:00:00Z", "event_id": "a"},
        ]
        # Tie-break: missing event_id ⇒ "" < "a", so missing comes first.
        ordered = sorted(events, key=_event_sort_key)
        assert ordered[0].get("event_id") in (None, "")


# ===========================================================================
# ghome_events end-to-end ordering through the tool
# ===========================================================================


class TestGhomeEventsOrdering:
    async def test_newest_first_through_tool(self, mock_client: MagicMock) -> None:
        mock_client.pull_events.return_value = [
            {"timestamp": "2026-05-23T10:00:00Z", "event_id": "oldest", "payload": {}},
            {"timestamp": "2026-05-23T12:00:00Z", "event_id": "newest", "payload": {}},
            {"timestamp": "2026-05-23T11:00:00Z", "event_id": "middle", "payload": {}},
        ]
        result = await ghome_events()
        # In rendered output, "newest" should appear before "middle" before "oldest".
        new_pos = result.find("newest")
        mid_pos = result.find("middle")
        old_pos = result.find("oldest")
        assert new_pos != -1 and mid_pos != -1 and old_pos != -1, f"Expected event_ids in output: {result}"
        assert new_pos < mid_pos < old_pos, f"Order wrong: {result}"

    async def test_tie_break_through_tool(self, mock_client: MagicMock) -> None:
        ts = "2026-05-23T10:00:00Z"
        mock_client.pull_events.return_value = [
            {"timestamp": ts, "event_id": "evt-b", "payload": {}},
            {"timestamp": ts, "event_id": "evt-a", "payload": {}},
        ]
        result = await ghome_events()
        a_pos = result.find("evt-a")
        b_pos = result.find("evt-b")
        assert a_pos != -1 and b_pos != -1
        assert a_pos < b_pos, f"Expected evt-a before evt-b: {result}"

    async def test_unparseable_timestamp_does_not_raise(self, mock_client: MagicMock) -> None:
        mock_client.pull_events.return_value = [
            {"timestamp": "garbage", "event_id": "evt-x", "payload": {}},
            {"timestamp": "2026-05-23T10:00:00Z", "event_id": "evt-y", "payload": {}},
        ]
        # Must not raise; both events should appear in output.
        result = await ghome_events()
        assert "evt-x" in result
        assert "evt-y" in result
