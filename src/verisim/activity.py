from __future__ import annotations

import heapq
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time as datetime_time, timedelta
from pathlib import Path
from random import Random
from typing import Literal, Protocol, TextIO
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from verisim.models import (
    CompanyRecord,
    OrderRecord,
    PersonRecord,
    ProductRecord,
    SupportTicketRecord,
    VerisimModel,
)
from verisim.types import CountryCode, EmailAddress, Username

ActivityKind = Literal["login", "purchase", "support_ticket"]
LoginMethod = Literal["password", "sso", "magic_link", "mfa"]
DeviceType = Literal["desktop", "mobile", "tablet"]

KAFKA_INSTALL_HINT = "Install optional Kafka dependencies with `verisim[kafka]`."


def _default_activity_mix() -> dict[ActivityKind, float]:
    return {"login": 0.72, "purchase": 0.2, "support_ticket": 0.08}


def _default_weekday_weights() -> dict[int, float]:
    return {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 0.35, 6: 0.25}


def _default_hour_weights() -> dict[int, float]:
    return {
        0: 0.05,
        1: 0.04,
        2: 0.03,
        3: 0.03,
        4: 0.04,
        5: 0.08,
        6: 0.18,
        7: 0.35,
        8: 0.75,
        9: 1.0,
        10: 0.95,
        11: 0.9,
        12: 0.8,
        13: 0.85,
        14: 0.9,
        15: 0.85,
        16: 0.75,
        17: 0.6,
        18: 0.42,
        19: 0.3,
        20: 0.22,
        21: 0.16,
        22: 0.1,
        23: 0.07,
    }


def _default_month_weights() -> dict[int, float]:
    return {month: 1.0 for month in range(1, 13)}


class SeasonalityProfile(VerisimModel):
    weekday_weights: dict[int, float] = Field(default_factory=_default_weekday_weights)
    hour_weights: dict[int, float] = Field(default_factory=_default_hour_weights)
    month_weights: dict[int, float] = Field(default_factory=_default_month_weights)

    @field_validator("weekday_weights")
    @classmethod
    def validate_weekday_weights(cls, values: dict[int, float]) -> dict[int, float]:
        return _validate_weight_map(values, "weekday weights", 0, 6)

    @field_validator("hour_weights")
    @classmethod
    def validate_hour_weights(cls, values: dict[int, float]) -> dict[int, float]:
        return _validate_weight_map(values, "hour weights", 0, 23)

    @field_validator("month_weights")
    @classmethod
    def validate_month_weights(cls, values: dict[int, float]) -> dict[int, float]:
        return _validate_weight_map(values, "month weights", 1, 12)

    def day_weight(self, value: date) -> float:
        return self.weekday_weights.get(value.weekday(), 0.0) * self.month_weights.get(
            value.month, 0.0
        )


class ActivityStreamSpec(VerisimModel):
    people: int = Field(default=1, ge=1)
    events_per_person: int = Field(default=100, ge=1)
    start_at: datetime | None = None
    end_at: datetime | None = None
    activity_mix: dict[ActivityKind, float] = Field(
        default_factory=_default_activity_mix
    )
    seasonality: SeasonalityProfile = Field(default_factory=SeasonalityProfile)

    @field_validator("activity_mix")
    @classmethod
    def validate_activity_mix(
        cls, values: dict[ActivityKind, float]
    ) -> dict[ActivityKind, float]:
        if not values or any(weight <= 0 for weight in values.values()):
            raise ValueError("activity mix weights must be positive")
        return values

    @model_validator(mode="after")
    def validate_window(self) -> "ActivityStreamSpec":
        if self.start_at is not None and self.end_at is not None:
            if _as_utc(self.start_at) >= _as_utc(self.end_at):
                raise ValueError("start_at must be before end_at")
        return self


class ActivityActor(VerisimModel):
    id: UUID
    name: str
    username: Username
    email: EmailAddress
    company_id: UUID
    company_name: str

    @classmethod
    def from_person_record(cls, record: PersonRecord) -> "ActivityActor":
        return cls(
            id=record.id,
            name=record.person.name,
            username=record.person.username,
            email=record.contact.email,
            company_id=record.company.id,
            company_name=record.company.name,
        )


class LoginPayload(VerisimModel):
    kind: Literal["login"] = "login"
    success: bool
    method: LoginMethod
    ip_address: str
    user_agent: str
    device: DeviceType
    country_code: CountryCode


class PurchasePayload(VerisimModel):
    kind: Literal["purchase"] = "purchase"
    order: OrderRecord


class SupportTicketPayload(VerisimModel):
    kind: Literal["support_ticket"] = "support_ticket"
    ticket: SupportTicketRecord


class ActivityEvent(VerisimModel):
    schema_version: Literal["1"] = "1"
    id: UUID
    sequence: int = Field(ge=1)
    person_sequence: int = Field(ge=1)
    kind: ActivityKind
    person: ActivityActor
    session_id: str | None
    occurred_at: str
    payload: LoginPayload | PurchasePayload | SupportTicketPayload


class StreamStats(VerisimModel):
    emitted: int = Field(ge=0)
    duration_seconds: float = Field(ge=0)


class ActivitySink(Protocol):
    def emit(self, event: ActivityEvent) -> None: ...

    def close(self) -> None: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class JsonlActivitySink:
    def __init__(self, stream: TextIO, *, close_stream: bool = False) -> None:
        self.stream = stream
        self.close_stream = close_stream

    @classmethod
    def from_path(cls, path: Path | str) -> "JsonlActivitySink":
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        return cls(output.open("w", encoding="utf-8"), close_stream=True)

    def emit(self, event: ActivityEvent) -> None:
        self.stream.write(f"{event.model_dump_json()}\n")

    def close(self) -> None:
        if self.close_stream:
            self.stream.close()
        else:
            self.stream.flush()


class KafkaDeliveryError(RuntimeError):
    pass


class KafkaActivitySink:
    def __init__(
        self,
        *,
        topic: str,
        bootstrap_servers: str | None = None,
        config: Mapping[str, object] | None = None,
        producer: object | None = None,
        max_queue_retries: int = 3,
        flush_timeout: float = 30.0,
    ) -> None:
        self.topic = topic
        self.max_queue_retries = max_queue_retries
        self.flush_timeout = flush_timeout
        self.delivery_errors: list[str] = []
        if producer is None:
            try:
                producer_cls = _import_kafka_producer()
            except ImportError as error:
                raise RuntimeError(KAFKA_INSTALL_HINT) from error
            producer_config = dict(config or {})
            if bootstrap_servers is not None:
                producer_config["bootstrap.servers"] = bootstrap_servers
            producer = producer_cls(producer_config)
        self.producer = producer

    def emit(self, event: ActivityEvent) -> None:
        value = event.model_dump_json().encode("utf-8")
        key = str(event.person.id).encode("utf-8")
        headers = [
            ("schema_version", event.schema_version),
            ("activity_kind", event.kind),
        ]
        retries = 0
        while True:
            try:
                self.producer.produce(
                    topic=self.topic,
                    key=key,
                    value=value,
                    headers=headers,
                    callback=self._delivery_report,
                )
                break
            except BufferError as error:
                retries += 1
                if retries > self.max_queue_retries:
                    raise KafkaDeliveryError("Kafka producer queue is full") from error
                self.producer.poll(1)
        self.producer.poll(0)
        self._raise_delivery_errors()

    def close(self) -> None:
        remaining = self.producer.flush(self.flush_timeout)
        self._raise_delivery_errors()
        if remaining:
            raise KafkaDeliveryError(
                f"Kafka producer closed with {remaining} undelivered messages"
            )

    def _delivery_report(self, error, message) -> None:
        del message
        if error is not None:
            self.delivery_errors.append(str(error))

    def _raise_delivery_errors(self) -> None:
        if not self.delivery_errors:
            return
        message = "; ".join(self.delivery_errors)
        self.delivery_errors.clear()
        raise KafkaDeliveryError(message)


def emit_activity_stream(
    events: Iterable[ActivityEvent],
    sink: ActivitySink,
    *,
    throughput_rps: float | None = None,
    clock: Clock | None = None,
) -> StreamStats:
    if throughput_rps is not None and throughput_rps <= 0:
        raise ValueError("throughput_rps must be greater than 0")
    active_clock = clock or RealClock()
    started_at = active_clock.monotonic()
    emitted = 0
    try:
        for event in events:
            if throughput_rps is not None:
                target_time = started_at + emitted / throughput_rps
                wait_seconds = target_time - active_clock.monotonic()
                if wait_seconds > 0:
                    active_clock.sleep(wait_seconds)
            sink.emit(event)
            emitted += 1
    finally:
        sink.close()
    return StreamStats(
        emitted=emitted,
        duration_seconds=max(0.0, active_clock.monotonic() - started_at),
    )


def iter_activity_stream(verisim, spec: ActivityStreamSpec) -> Iterable[ActivityEvent]:
    start_at, end_at = _resolve_window(spec)
    actors = [verisim.generate(PersonRecord) for _ in range(spec.people)]
    merchant_record = verisim.generate(CompanyRecord)
    product_record = verisim.generate(
        ProductRecord,
        context={"company_record": merchant_record},
        mode="repair",
    )

    heap: list[_QueuedActivity] = []
    for index, actor in enumerate(actors):
        timeline = _PersonTimeline(
            random=Random(verisim.random.randrange(0, 2**63)),
            spec=spec,
            person_index=index,
            actor=actor,
            start_at=start_at,
            end_at=end_at,
        )
        try:
            scheduled = next(timeline)
        except StopIteration:  # pragma: no cover - spec validation prevents this
            continue
        heapq.heappush(
            heap,
            _QueuedActivity(
                occurred_at=scheduled.occurred_at,
                person_index=index,
                scheduled=scheduled,
                timeline=timeline,
            ),
        )

    sequence = 0
    while heap:
        queued = heapq.heappop(heap)
        sequence += 1
        yield _activity_event(
            verisim=verisim,
            scheduled=queued.scheduled,
            sequence=sequence,
            merchant_record=merchant_record,
            product_record=product_record,
        )
        try:
            next_scheduled = next(queued.timeline)
        except StopIteration:
            continue
        heapq.heappush(
            heap,
            _QueuedActivity(
                occurred_at=next_scheduled.occurred_at,
                person_index=queued.person_index,
                scheduled=next_scheduled,
                timeline=queued.timeline,
            ),
        )


@dataclass(order=True)
class _QueuedActivity:
    occurred_at: datetime
    person_index: int
    scheduled: "_ScheduledActivity" = field(compare=False)
    timeline: "_PersonTimeline" = field(compare=False)


@dataclass(frozen=True)
class _ScheduledActivity:
    occurred_at: datetime
    person_sequence: int
    kind: ActivityKind
    actor: PersonRecord
    session_id: str | None


class _PersonTimeline:
    def __init__(
        self,
        *,
        random: Random,
        spec: ActivityStreamSpec,
        person_index: int,
        actor: PersonRecord,
        start_at: datetime,
        end_at: datetime,
    ) -> None:
        self.random = random
        self.spec = spec
        self.person_index = person_index
        self.actor = actor
        self.produced = 0
        self.sampler = _ActivityTimelineSampler(
            random=random,
            start_at=start_at,
            end_at=end_at,
            total_events=spec.events_per_person,
            seasonality=spec.seasonality,
        )

    def __iter__(self) -> "_PersonTimeline":
        return self

    def __next__(self) -> _ScheduledActivity:
        if self.produced >= self.spec.events_per_person:
            raise StopIteration
        self.produced += 1
        kind = _weighted_choice(self.random, self.spec.activity_mix)
        session_id = _session_id(self.actor, self.produced, kind)
        return _ScheduledActivity(
            occurred_at=self.sampler.next_timestamp(self.produced),
            person_sequence=self.produced,
            kind=kind,
            actor=self.actor,
            session_id=session_id,
        )


class _ActivityTimelineSampler:
    def __init__(
        self,
        *,
        random: Random,
        start_at: datetime,
        end_at: datetime,
        total_events: int,
        seasonality: SeasonalityProfile,
    ) -> None:
        self.random = random
        self.start_at = start_at
        self.end_at = end_at
        self.total_events = total_events
        self.seasonality = seasonality
        self.previous: datetime | None = None
        total_seconds = max(1.0, (end_at - start_at).total_seconds())
        self.mean_gap_seconds = max(1.0, total_seconds / (total_events + 1))

    def next_timestamp(self, sequence: int) -> datetime:
        if self.previous is None:
            candidate = self.start_at + timedelta(
                seconds=self.random.random() * self.mean_gap_seconds
            )
        else:
            candidate = self.previous + timedelta(seconds=self._gap_seconds())

        remaining = self.total_events - sequence
        minimum = self.start_at if self.previous is None else self.previous
        reserve_seconds = remaining * min(self.mean_gap_seconds, 86_400)
        latest = self.end_at - timedelta(seconds=reserve_seconds)
        if latest < minimum:
            latest = self.end_at
        if candidate > latest:
            span = max(0.0, (latest - minimum).total_seconds())
            candidate = minimum + timedelta(seconds=self.random.random() * span)
        if candidate < minimum:
            candidate = minimum

        timestamp = self._seasonal_timestamp(candidate, latest)
        self.previous = timestamp
        return timestamp

    def _gap_seconds(self) -> float:
        return self.random.lognormvariate(0.0, 0.9) * self.mean_gap_seconds

    def _seasonal_timestamp(self, candidate: datetime, latest: datetime) -> datetime:
        candidate = candidate.replace(microsecond=0)
        latest = latest.replace(microsecond=0)
        day_choices: list[
            tuple[date, float, datetime, datetime, list[tuple[int, float]]]
        ] = []
        max_search_days = min(31, max(0, (latest.date() - candidate.date()).days))
        for offset in range(max_search_days + 1):
            day = candidate.date() + timedelta(days=offset)
            low = max(
                candidate,
                datetime.combine(day, datetime_time.min, tzinfo=candidate.tzinfo),
            )
            high = min(
                latest,
                datetime.combine(day, datetime_time.max, tzinfo=candidate.tzinfo),
            )
            weight = self.seasonality.day_weight(day)
            hour_choices = self._hour_choices(day, low, high)
            if weight > 0 and low <= high and hour_choices:
                day_choices.append((day, weight, low, high, hour_choices))

        if not day_choices:
            if self.previous is not None:
                retry_candidate = (self.previous + timedelta(seconds=1)).replace(
                    microsecond=0
                )
                if retry_candidate < candidate:
                    return self._seasonal_timestamp(retry_candidate, self.end_at)
            if latest < self.end_at:
                return self._seasonal_timestamp(candidate, self.end_at)
            return min(max(candidate, self.start_at), self.end_at)

        day, _, low, high, hour_choices = _weighted_item(self.random, day_choices)
        hour = _weighted_item(self.random, hour_choices)
        timestamp = datetime.combine(
            day,
            datetime_time(
                hour=hour,
                minute=self.random.randint(0, 59),
                second=self.random.randint(0, 59),
            ),
            tzinfo=candidate.tzinfo,
        )
        if timestamp < low:
            timestamp = low
        if timestamp > high:
            timestamp = high
        return timestamp.replace(microsecond=0)

    def _hour_choices(
        self, day: date, low: datetime, high: datetime
    ) -> list[tuple[int, float]]:
        hour_choices: list[tuple[int, float]] = []
        for hour, weight in self.seasonality.hour_weights.items():
            hour_start = datetime.combine(
                day, datetime_time(hour=hour), tzinfo=low.tzinfo
            )
            hour_end = hour_start + timedelta(hours=1, microseconds=-1)
            if weight > 0 and hour_start <= high and hour_end >= low:
                hour_choices.append((hour, weight))
        return hour_choices


def _activity_event(
    *,
    verisim,
    scheduled: _ScheduledActivity,
    sequence: int,
    merchant_record,
    product_record: ProductRecord,
) -> ActivityEvent:
    occurred_at = _iso_datetime(scheduled.occurred_at)
    return ActivityEvent(
        id=verisim.registry.uuid("activity_event"),
        sequence=sequence,
        person_sequence=scheduled.person_sequence,
        kind=scheduled.kind,
        person=ActivityActor.from_person_record(scheduled.actor),
        session_id=scheduled.session_id,
        occurred_at=occurred_at,
        payload=_payload_for_activity(
            verisim=verisim,
            scheduled=scheduled,
            occurred_at=occurred_at,
            merchant_record=merchant_record,
            product_record=product_record,
        ),
    )


def _payload_for_activity(
    *,
    verisim,
    scheduled: _ScheduledActivity,
    occurred_at: str,
    merchant_record,
    product_record: ProductRecord,
) -> LoginPayload | PurchasePayload | SupportTicketPayload:
    if scheduled.kind == "login":
        return _login_payload(verisim.random, scheduled.actor)
    if scheduled.kind == "purchase":
        order = verisim.generate(
            OrderRecord,
            context={
                "person_record": scheduled.actor,
                "company_record": merchant_record,
                "product_record": product_record,
            },
            mode="repair",
        )
        return PurchasePayload(
            order=_order_at(order, _parse_iso(occurred_at), verisim.random)
        )
    ticket = verisim.generate(
        SupportTicketRecord,
        context={
            "person_record": scheduled.actor,
            "company": scheduled.actor.company,
        },
        mode="repair",
    )
    return SupportTicketPayload(
        ticket=_ticket_at(ticket, _parse_iso(occurred_at), verisim.random)
    )


def _login_payload(random: Random, actor: PersonRecord) -> LoginPayload:
    return LoginPayload(
        success=random.random() > 0.03,
        method=random.choice(("password", "sso", "magic_link", "mfa")),
        ip_address=f"203.0.113.{random.randint(1, 254)}",
        user_agent=random.choice(
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)",
                "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36",
            )
        ),
        device=random.choice(("desktop", "mobile", "tablet")),
        country_code=actor.address.country_code,
    )


def _order_at(order: OrderRecord, occurred_at: datetime, random: Random) -> OrderRecord:
    fulfilled_at = None
    updated_at = occurred_at
    if order.fulfilled_at is not None:
        fulfilled = occurred_at + timedelta(days=random.randint(1, 7))
        fulfilled_at = _iso_datetime(fulfilled)
        updated_at = fulfilled
    return order.model_copy(
        update={
            "ordered_at": _iso_datetime(occurred_at),
            "updated_at": _iso_datetime(updated_at),
            "fulfilled_at": fulfilled_at,
        }
    )


def _ticket_at(
    ticket: SupportTicketRecord, occurred_at: datetime, random: Random
) -> SupportTicketRecord:
    first_response = occurred_at + timedelta(minutes=random.randint(10, 240))
    resolved_at = None
    if ticket.resolved_at is not None:
        resolved_at = _iso_datetime(
            first_response + timedelta(hours=random.randint(1, 72))
        )
    return ticket.model_copy(
        update={
            "opened_at": _iso_datetime(occurred_at),
            "first_response_at": _iso_datetime(first_response),
            "resolved_at": resolved_at,
            "resolution_summary": (
                None
                if resolved_at is None
                else (
                    f"Resolved {ticket.category} request for "
                    f"{ticket.requester.person.name}."
                )
            ),
        }
    )


def _resolve_window(spec: ActivityStreamSpec) -> tuple[datetime, datetime]:
    if spec.start_at is None and spec.end_at is None:
        end_at = datetime.now(UTC).replace(microsecond=0)
        start_at = end_at - timedelta(days=30)
        return start_at, end_at
    if spec.start_at is None:
        end_at = _as_utc(spec.end_at)
        return end_at - timedelta(days=30), end_at
    if spec.end_at is None:
        start_at = _as_utc(spec.start_at)
        return start_at, start_at + timedelta(days=30)
    return _as_utc(spec.start_at), _as_utc(spec.end_at)


def _session_id(actor: PersonRecord, sequence: int, kind: ActivityKind) -> str | None:
    if kind == "support_ticket":
        return None
    return f"sess_{actor.id.hex[:12]}_{sequence:04d}"


def _validate_weight_map(
    values: dict[int, float], label: str, minimum: int, maximum: int
) -> dict[int, float]:
    if not values:
        raise ValueError(f"{label} must not be empty")
    if any(key < minimum or key > maximum for key in values):
        raise ValueError(f"{label} keys must be between {minimum} and {maximum}")
    if any(weight <= 0 for weight in values.values()):
        raise ValueError(f"{label} must use positive weights")
    return values


def _weighted_choice(
    random: Random, weights: Mapping[ActivityKind, float]
) -> ActivityKind:
    return _weighted_item(random, list(weights.items()))


def _weighted_item(random: Random, items):
    total = sum(item[1] for item in items)
    pick = random.random() * total
    seen = 0.0
    for item in items:
        seen += item[1]
        if pick <= seen:
            return item[0] if len(item) == 2 else item
    fallback = items[-1]
    return fallback[0] if len(fallback) == 2 else fallback


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        raise ValueError("datetime value is required")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_datetime(value: datetime) -> str:
    return _as_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _import_kafka_producer():
    from confluent_kafka import Producer

    return Producer


__all__ = [
    "ActivityActor",
    "ActivityEvent",
    "ActivityKind",
    "ActivitySink",
    "ActivityStreamSpec",
    "JsonlActivitySink",
    "KafkaActivitySink",
    "KafkaDeliveryError",
    "LoginPayload",
    "PurchasePayload",
    "RealClock",
    "SeasonalityProfile",
    "StreamStats",
    "SupportTicketPayload",
    "emit_activity_stream",
    "iter_activity_stream",
]
