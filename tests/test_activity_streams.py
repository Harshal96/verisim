from __future__ import annotations

import json
from datetime import UTC, datetime
from io import StringIO

import pytest

from verisim import (
    ActivityStreamSpec,
    JsonlActivitySink,
    KafkaActivitySink,
    SeasonalityProfile,
    Verisim,
    emit_activity_stream,
)

WINDOW_START = datetime(2026, 5, 4, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 5, 8, 23, 59, tzinfo=UTC)


def test_activity_stream_spec_validates_counts_window_and_weights():
    with pytest.raises(ValueError):
        ActivityStreamSpec(people=0)

    with pytest.raises(ValueError, match="start_at must be before end_at"):
        ActivityStreamSpec(start_at=WINDOW_END, end_at=WINDOW_START)

    with pytest.raises(ValueError, match="activity mix weights"):
        ActivityStreamSpec(activity_mix={"login": 0})

    with pytest.raises(ValueError, match="hour weights"):
        SeasonalityProfile(hour_weights={24: 1})

    with pytest.raises(ValueError, match="throughput_rps"):
        emit_activity_stream([], JsonlActivitySink(StringIO()), throughput_rps=0)


def test_activity_stream_is_deterministic_chronological_and_seasonal():
    spec = ActivityStreamSpec(
        people=2,
        events_per_person=4,
        start_at=WINDOW_START,
        end_at=WINDOW_END,
        activity_mix={"login": 1},
        seasonality=SeasonalityProfile(
            weekday_weights={0: 1, 1: 1, 2: 1, 3: 1, 4: 1},
            hour_weights={9: 1},
            month_weights={5: 1},
        ),
    )

    first = list(Verisim(locale="en_US", seed=42).iter_activity_stream(spec))
    second = list(Verisim(locale="en_US", seed=42).iter_activity_stream(spec))

    assert [event.model_dump(mode="json") for event in first] == [
        event.model_dump(mode="json") for event in second
    ]
    assert len(first) == 8
    assert [event.occurred_at for event in first] == sorted(
        event.occurred_at for event in first
    )
    assert {event.kind for event in first} == {"login"}
    assert all(_parse(event.occurred_at).hour == 9 for event in first)
    assert all(_parse(event.occurred_at).month == 5 for event in first)
    assert all(
        WINDOW_START <= _parse(event.occurred_at) <= WINDOW_END for event in first
    )

    per_person_sequences: dict[str, list[int]] = {}
    for event in first:
        per_person_sequences.setdefault(str(event.person.id), []).append(
            event.person_sequence
        )
    assert sorted(per_person_sequences.values()) == [[1, 2, 3, 4], [1, 2, 3, 4]]


def test_activity_payloads_match_envelope_actor_and_timestamp():
    purchase_spec = ActivityStreamSpec(
        people=1,
        events_per_person=1,
        start_at=WINDOW_START,
        end_at=WINDOW_END,
        activity_mix={"purchase": 1},
    )
    purchase = next(
        Verisim(locale="en_US", seed=101).iter_activity_stream(purchase_spec)
    )

    assert purchase.kind == "purchase"
    assert purchase.payload.order.buyer.id == purchase.person.id
    assert purchase.payload.order.ordered_at == purchase.occurred_at
    assert purchase.payload.order.updated_at >= purchase.occurred_at

    ticket_spec = ActivityStreamSpec(
        people=1,
        events_per_person=1,
        start_at=WINDOW_START,
        end_at=WINDOW_END,
        activity_mix={"support_ticket": 1},
    )
    ticket = next(Verisim(locale="en_US", seed=102).iter_activity_stream(ticket_spec))

    assert ticket.kind == "support_ticket"
    assert ticket.payload.ticket.requester.id == ticket.person.id
    assert ticket.payload.ticket.opened_at == ticket.occurred_at
    assert ticket.payload.ticket.first_response_at >= ticket.occurred_at


def test_jsonl_sink_and_paced_emitter_write_stream_without_materializing():
    spec = ActivityStreamSpec(
        people=1,
        events_per_person=3,
        start_at=WINDOW_START,
        end_at=WINDOW_END,
        activity_mix={"login": 1},
    )
    events = Verisim(locale="en_US", seed=55).iter_activity_stream(spec)
    stream = StringIO()
    clock = FakeClock()

    stats = emit_activity_stream(
        events,
        JsonlActivitySink(stream),
        throughput_rps=2,
        clock=clock,
    )

    lines = stream.getvalue().splitlines()
    assert stats.emitted == 3
    assert len(lines) == 3
    assert all(json.loads(line)["kind"] == "login" for line in lines)
    assert clock.sleeps == [0.5, 0.5]


def test_kafka_sink_publishes_json_with_person_key_and_flushes():
    event = next(
        Verisim(locale="en_US", seed=60).iter_activity_stream(
            ActivityStreamSpec(
                people=1,
                events_per_person=1,
                start_at=WINDOW_START,
                end_at=WINDOW_END,
                activity_mix={"login": 1},
            )
        )
    )
    producer = FakeProducer()

    sink = KafkaActivitySink(topic="activity-events", producer=producer)
    sink.emit(event)
    sink.close()

    assert len(producer.produced) == 1
    produced = producer.produced[0]
    assert produced["topic"] == "activity-events"
    assert produced["key"] == str(event.person.id).encode("utf-8")
    assert json.loads(produced["value"].decode("utf-8"))["id"] == str(event.id)
    assert ("activity_kind", event.kind) in produced["headers"]
    assert producer.polls == [0]
    assert producer.flushed is True


def test_kafka_sink_retries_local_queue_backpressure():
    event = next(
        Verisim(locale="en_US", seed=61).iter_activity_stream(
            ActivityStreamSpec(
                people=1,
                events_per_person=1,
                start_at=WINDOW_START,
                end_at=WINDOW_END,
                activity_mix={"login": 1},
            )
        )
    )
    producer = FakeProducer(buffer_errors=1)

    sink = KafkaActivitySink(topic="activity-events", producer=producer)
    sink.emit(event)

    assert producer.polls == [1, 0]
    assert len(producer.produced) == 1


def test_kafka_sink_reports_missing_optional_dependency(monkeypatch):
    import verisim.activity as activity

    def missing_producer():
        raise ImportError("missing")

    monkeypatch.setattr(activity, "_import_kafka_producer", missing_producer)

    with pytest.raises(RuntimeError, match=r"verisim\[kafka\]"):
        KafkaActivitySink(
            topic="activity-events",
            bootstrap_servers="localhost:9092",
        )


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeProducer:
    def __init__(self, buffer_errors: int = 0) -> None:
        self.buffer_errors = buffer_errors
        self.produced: list[dict[str, object]] = []
        self.polls: list[float] = []
        self.flushed = False

    def produce(self, **kwargs) -> None:
        if self.buffer_errors:
            self.buffer_errors -= 1
            raise BufferError("queue full")
        self.produced.append(kwargs)

    def poll(self, timeout: float) -> None:
        self.polls.append(timeout)

    def flush(self, timeout: float | None = None) -> int:
        del timeout
        self.flushed = True
        return 0


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
