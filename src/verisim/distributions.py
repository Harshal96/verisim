from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from random import Random
from types import UnionType
from typing import Annotated, Any, Literal, TypeAlias, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from verisim.errors import ProfileValidationError

NoneType = type(None)


class ProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WeightedChoice(ProfileModel):
    kind: Literal["weighted_choice"] = "weighted_choice"
    values: dict[str, float]

    @field_validator("values")
    @classmethod
    def validate_weights(cls, values: dict[str, float]) -> dict[str, float]:
        if not values:
            raise ValueError("weighted choices must not be empty")
        if any(weight <= 0 for weight in values.values()):
            raise ValueError("weighted choices must use positive weights")
        return values

    def sample(self, random: Random) -> str:
        total = sum(self.values.values())
        pick = random.random() * total
        seen = 0.0
        for value, weight in self.values.items():
            seen += weight
            if pick <= seen:
                return value
        return next(reversed(self.values))


class NormalInt(ProfileModel):
    kind: Literal["normal_int"] = "normal_int"
    mean: float
    stdev: float = Field(gt=0)
    minimum: int
    maximum: int

    @model_validator(mode="after")
    def validate_bounds(self) -> "NormalInt":
        if self.minimum > self.maximum:
            raise ValueError("minimum must be less than or equal to maximum")
        return self

    def sample(self, random: Random) -> int:
        if self.minimum == self.maximum:
            return self.minimum
        value = int(round(random.gauss(self.mean, self.stdev)))
        return max(self.minimum, min(self.maximum, value))


class NormalFloat(ProfileModel):
    kind: Literal["normal_float"] = "normal_float"
    mean: float
    stdev: float = Field(gt=0)
    minimum: float
    maximum: float

    @model_validator(mode="after")
    def validate_bounds(self) -> "NormalFloat":
        if self.minimum > self.maximum:
            raise ValueError("minimum must be less than or equal to maximum")
        return self

    def sample(self, random: Random) -> float:
        if self.minimum == self.maximum:
            return self.minimum
        value = random.gauss(self.mean, self.stdev)
        return max(self.minimum, min(self.maximum, value))


class NormalDate(ProfileModel):
    kind: Literal["normal_date"] = "normal_date"
    center: date
    stdev_days: float = Field(gt=0)
    minimum: date
    maximum: date

    @model_validator(mode="after")
    def validate_bounds(self) -> "NormalDate":
        if self.minimum > self.maximum:
            raise ValueError("minimum must be less than or equal to maximum")
        return self

    def sample(self, random: Random) -> date:
        if self.minimum == self.maximum:
            return self.minimum
        offset = int(round(random.gauss(0, self.stdev_days)))
        value = self.center + timedelta(days=offset)
        return max(self.minimum, min(self.maximum, value))


class ParetoInt(ProfileModel):
    kind: Literal["pareto_int"] = "pareto_int"
    minimum: int = Field(ge=0)
    shape: float = Field(gt=0)
    maximum: int | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> "ParetoInt":
        if self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum must be less than or equal to maximum")
        return self

    def sample(self, random: Random) -> int:
        if self.maximum is not None and self.minimum == self.maximum:
            return self.minimum
        scale = max(1, self.minimum)
        value = int(round(random.paretovariate(self.shape) * scale))
        value = max(self.minimum, value)
        return min(self.maximum, value) if self.maximum is not None else value


class ParetoFloat(ProfileModel):
    kind: Literal["pareto_float"] = "pareto_float"
    minimum: float = Field(ge=0)
    shape: float = Field(gt=0)
    maximum: float | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> "ParetoFloat":
        if self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum must be less than or equal to maximum")
        return self

    def sample(self, random: Random) -> float:
        if self.maximum is not None and self.minimum == self.maximum:
            return self.minimum
        scale = max(1.0, self.minimum)
        value = max(self.minimum, random.paretovariate(self.shape) * scale)
        return min(self.maximum, value) if self.maximum is not None else value


class DateTimeWindow(ProfileModel):
    kind: Literal["datetime_window"] = "datetime_window"
    start: datetime
    end: datetime
    weekday_weights: dict[int, float] | None = None

    @field_validator("weekday_weights")
    @classmethod
    def validate_weekdays(
        cls, values: dict[int, float] | None
    ) -> dict[int, float] | None:
        if values is None:
            return values
        if not values:
            raise ValueError("weekday weights must not be empty")
        if any(day < 0 or day > 6 for day in values):
            raise ValueError("weekday keys must be between 0 and 6")
        if any(weight <= 0 for weight in values.values()):
            raise ValueError("weekday weights must use positive weights")
        return values

    @model_validator(mode="after")
    def validate_bounds(self) -> "DateTimeWindow":
        if self.start > self.end:
            raise ValueError("start must be before end")
        return self

    def sample(self, random: Random) -> datetime:
        if self.weekday_weights is None:
            total_seconds = max(0.0, (self.end - self.start).total_seconds())
            return self.start + timedelta(seconds=random.random() * total_seconds)

        candidates = [
            self.start.date() + timedelta(days=offset)
            for offset in range((self.end.date() - self.start.date()).days + 1)
            if (self.start.date() + timedelta(days=offset)).weekday()
            in self.weekday_weights
        ]
        if not candidates:
            raise ProfileValidationError("datetime window has no weighted weekdays")

        picked_date = _weighted_choice(
            random,
            [
                (candidate, self.weekday_weights[candidate.weekday()])
                for candidate in candidates
            ],
        )
        day_start = datetime.combine(picked_date, time.min, tzinfo=self._tzinfo())
        day_end = datetime.combine(picked_date, time.max, tzinfo=self._tzinfo())
        low = max(self.start, day_start)
        high = min(self.end, day_end)
        total_seconds = max(0.0, (high - low).total_seconds())
        return low + timedelta(seconds=random.random() * total_seconds)

    def _tzinfo(self) -> object:
        return self.start.tzinfo or self.end.tzinfo or UTC


Distribution: TypeAlias = Annotated[
    WeightedChoice
    | NormalInt
    | NormalFloat
    | NormalDate
    | ParetoInt
    | ParetoFloat
    | DateTimeWindow,
    Field(discriminator="kind"),
]


class FieldRule(ProfileModel):
    distribution: Distribution | None = None
    null_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class Predicate(ProfileModel):
    path: str
    op: Literal["eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in", "exists"]
    value: object | None = None


class ConditionalRule(ProfileModel):
    when: list[Predicate] = Field(min_length=1)
    apply: dict[str, FieldRule] = Field(default_factory=dict)


class CollectionRule(ProfileModel):
    length: int = Field(default=1, ge=0)


class StatisticalProfile(ProfileModel):
    fields: dict[str, FieldRule] = Field(default_factory=dict)
    correlations: list[ConditionalRule] = Field(default_factory=list)
    collections: dict[str, CollectionRule] = Field(default_factory=dict)

    def rule_for(
        self,
        path: str,
        lookup: Callable[[str], object],
    ) -> FieldRule | None:
        rule = self.fields.get(path)
        for correlation in self.correlations:
            if all(
                _predicate_matches(predicate, lookup) for predicate in correlation.when
            ):
                rule = correlation.apply.get(path, rule)
        return rule

    def collection_for(self, path: str) -> CollectionRule | None:
        return self.collections.get(path)

    def validate_null_rates_for_model(self, model: type[BaseModel]) -> None:
        for path, rule in self.fields.items():
            if path.endswith("[]") or rule.null_rate == 0:
                continue
            annotation = _annotation_for_path(model, path)
            if annotation is not None and not is_nullable_annotation(annotation):
                raise ProfileValidationError(
                    f"field {path!r} is not nullable and cannot use a null rate"
                )


class StatisticalSampler:
    def __init__(self, profile: StatisticalProfile | None = None) -> None:
        self.profile = profile or StatisticalProfile()
        self.values: dict[str, object] = {}

    def has_rule(self, path: str, facts: Mapping[str, object]) -> bool:
        return (
            self.profile.rule_for(path, lambda candidate: self.lookup(candidate, facts))
            is not None
        )

    def sample_field(
        self,
        path: str,
        random: Random,
        facts: Mapping[str, object],
        default: Callable[[], object],
        annotation: object | None = None,
    ) -> object:
        rule = self.profile.rule_for(
            path, lambda candidate: self.lookup(candidate, facts)
        )
        if rule is None:
            value = default()
            self.values[path] = value
            return value

        if rule.null_rate and random.random() < rule.null_rate:
            if annotation is not None and not is_nullable_annotation(annotation):
                raise ProfileValidationError(
                    f"field {path!r} is not nullable and cannot use a null rate"
                )
            self.values[path] = None
            return None

        if rule.distribution is None:
            value = default()
        else:
            value = rule.distribution.sample(random)
        self.values[path] = value
        return value

    def lookup(self, path: str, facts: Mapping[str, object]) -> object:
        if path in self.values:
            return self.values[path]
        if path == "person.age":
            person = facts.get("person")
            birthdate = getattr(person, "birthdate", None)
            if isinstance(birthdate, str) and len(birthdate) >= 4:
                return date.today().year - int(birthdate[:4])
        if path == "company.size_band" and "size_band" in facts:
            return facts["size_band"]
        parts = path.split(".")
        current = facts.get(parts[0])
        if current is None and parts[0] == "company":
            current = facts.get("company_record") or facts.get("company")
        for part in parts[1:]:
            if current is None:
                return None
            if isinstance(current, Mapping):
                current = current.get(part)
            else:
                current = getattr(current, part, None)
        return current


def is_nullable_annotation(annotation: object) -> bool:
    annotation = _unwrap_annotated(annotation)
    origin = get_origin(annotation)
    if origin in {UnionType, getattr(__import__("typing"), "Union")}:
        return any(argument is NoneType for argument in get_args(annotation))
    return annotation is NoneType


def _annotation_for_path(model: type[BaseModel], path: str) -> object | None:
    paths = [path]
    prefix = _root_prefix_for_model(model)
    if prefix and path.startswith(f"{prefix}."):
        paths.append(path[len(prefix) + 1 :])

    for candidate in paths:
        annotation = _annotation_for_parts(model, candidate.split("."))
        if annotation is not None:
            return annotation
    return None


def _annotation_for_parts(model: type[BaseModel], parts: list[str]) -> object | None:
    current: object = model
    for raw_part in parts:
        part = raw_part.removesuffix("[]")
        if not isinstance(current, type) or not issubclass(current, BaseModel):
            return None
        field = current.model_fields.get(part)
        if field is None:
            return None
        annotation = field.annotation
        if raw_part.endswith("[]"):
            annotation = _sequence_item_annotation(annotation)
        current = _unwrap_annotated(annotation)
    return current


def _sequence_item_annotation(annotation: object) -> object:
    annotation = _unwrap_annotated(annotation)
    args = get_args(annotation)
    return args[0] if args else object


def _root_prefix_for_model(model: type[BaseModel]) -> str | None:
    name = model.__name__
    if name == "Company":
        return "company"
    if name == "CompanyRecord":
        return "company"
    if name == "Person":
        return "person"
    if name == "PersonRecord":
        return "person_record"
    if name == "ProductRecord":
        return "product"
    return None


def _unwrap_annotated(annotation: object) -> object:
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    return annotation


def _predicate_matches(predicate: Predicate, lookup: Callable[[str], object]) -> bool:
    actual = lookup(predicate.path)
    if predicate.op == "exists":
        return actual is not None
    if predicate.op == "eq":
        return actual == predicate.value
    if predicate.op == "ne":
        return actual != predicate.value
    if predicate.op == "lt":
        return actual is not None and actual < predicate.value  # type: ignore[operator]
    if predicate.op == "lte":
        return actual is not None and actual <= predicate.value  # type: ignore[operator]
    if predicate.op == "gt":
        return actual is not None and actual > predicate.value  # type: ignore[operator]
    if predicate.op == "gte":
        return actual is not None and actual >= predicate.value  # type: ignore[operator]
    if predicate.op == "in":
        return actual in predicate.value  # type: ignore[operator]
    if predicate.op == "not_in":
        return actual not in predicate.value  # type: ignore[operator]
    return False


def _weighted_choice(random: Random, choices: list[tuple[Any, float]]) -> Any:
    total = sum(weight for _, weight in choices)
    pick = random.random() * total
    seen = 0.0
    for value, weight in choices:
        seen += weight
        if pick <= seen:
            return value
    return choices[-1][0]


__all__ = [
    "CollectionRule",
    "ConditionalRule",
    "DateTimeWindow",
    "FieldRule",
    "NormalDate",
    "NormalFloat",
    "NormalInt",
    "ParetoFloat",
    "ParetoInt",
    "Predicate",
    "StatisticalProfile",
    "StatisticalSampler",
    "WeightedChoice",
    "is_nullable_annotation",
]
