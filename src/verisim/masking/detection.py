from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from verisim.masking.types import MaskingConfig, PIIColumn, PIIKind

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
IDENTIFIER_SPLIT_RE = re.compile(r"[^a-z0-9]+")
STREET_WORDS = {
    "avenue",
    "ave",
    "boulevard",
    "blvd",
    "circle",
    "court",
    "ct",
    "drive",
    "dr",
    "lane",
    "ln",
    "road",
    "rd",
    "street",
    "st",
    "way",
}


def detect_pii_columns(
    rows: Iterable[Mapping[str, object]], config: MaskingConfig
) -> tuple[PIIColumn, ...]:
    row_list = list(rows)
    column_names = _column_names(row_list)
    detected: list[PIIColumn] = []
    overrides = dict(config.column_overrides or {})

    for name in column_names:
        if name in overrides:
            kind = overrides[name]
            if kind is not None:
                detected.append(
                    PIIColumn(
                        name=name,
                        kind=kind,
                        confidence=1.0,
                        reasons=("manual override",),
                    )
                )
            continue

        name_match = _classify_column_name(name)
        sample_match = _classify_sample_values(
            [row.get(name) for row in row_list[: config.sample_size]]
        )
        candidate = _merge_matches(name_match, sample_match)
        if candidate is None:
            continue
        kind, confidence, reasons = candidate
        if confidence >= config.min_confidence:
            detected.append(
                PIIColumn(
                    name=name,
                    kind=kind,
                    confidence=confidence,
                    reasons=tuple(reasons),
                )
            )

    return tuple(detected)


def _column_names(rows: list[Mapping[str, object]]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for name in row:
            if name not in seen:
                seen.add(name)
                ordered.append(str(name))
    return tuple(ordered)


def _classify_column_name(name: str) -> tuple[PIIKind, float, str] | None:
    normalized = _normalize_identifier(name)
    tokens = tuple(token for token in normalized.split("_") if token)
    token_set = set(tokens)

    if "email" in token_set or "mail" in token_set:
        return "email", 0.9, "column name suggests email"
    if token_set & {"phone", "mobile", "cell", "telephone", "tel"}:
        return "phone", 0.9, "column name suggests phone"
    if token_set & {"zip", "zipcode", "postal", "postcode"}:
        return "postal_code", 0.85, "column name suggests postal code"
    if "country" in token_set and "code" in token_set:
        return "country_code", 0.85, "column name suggests country code"
    if "country" in token_set:
        return "country", 0.8, "column name suggests country"
    if token_set & {"state", "province", "region"} and "code" in token_set:
        return "region_code", 0.85, "column name suggests region code"
    if token_set & {"state", "province", "region"}:
        return "region", 0.8, "column name suggests region"
    if "city" in token_set or "town" in token_set:
        return "city", 0.8, "column name suggests city"
    if token_set & {"address", "addr", "street"}:
        return "address_line1", 0.85, "column name suggests street address"
    if token_set & {"first", "given"} and "name" in token_set:
        return "given_name", 0.85, "column name suggests given name"
    if token_set & {"last", "family", "surname"} and "name" in token_set:
        return "family_name", 0.85, "column name suggests family name"
    if "name" in token_set and "username" not in token_set:
        return "name", 0.8, "column name suggests person name"
    return None


def _classify_sample_values(
    values: Iterable[object],
) -> tuple[PIIKind, float, str] | None:
    samples = [
        text
        for value in values
        if value is not None
        for text in (" ".join(str(value).strip().split()),)
        if text
    ]
    if not samples:
        return None

    scored: list[tuple[PIIKind, float, str]] = []
    if _ratio(samples, _looks_like_email) >= 0.6:
        scored.append(("email", 0.85, "sample values look like email addresses"))
    if _ratio(samples, _looks_like_phone) >= 0.6:
        scored.append(("phone", 0.8, "sample values look like phone numbers"))
    if _ratio(samples, _looks_like_street_address) >= 0.6:
        scored.append(("address_line1", 0.75, "sample values look like addresses"))
    if _ratio(samples, _looks_like_name) >= 0.6:
        scored.append(("name", 0.7, "sample values look like person names"))

    return max(scored, key=lambda item: item[1]) if scored else None


def _merge_matches(
    name_match: tuple[PIIKind, float, str] | None,
    sample_match: tuple[PIIKind, float, str] | None,
) -> tuple[PIIKind, float, list[str]] | None:
    if name_match is None:
        if sample_match is None:
            return None
        kind, confidence, reason = sample_match
        return kind, confidence, [reason]
    kind, name_confidence, name_reason = name_match
    reasons = [name_reason]
    confidence = name_confidence
    if sample_match is not None:
        sample_kind, sample_confidence, sample_reason = sample_match
        if sample_kind == kind:
            confidence = min(0.99, confidence + 0.1)
            reasons.append(sample_reason)
        else:
            confidence = max(0.0, confidence - 0.05)
            reasons.append(f"sample values weakly suggest {sample_kind}")
    return kind, confidence, reasons


def _normalize_identifier(value: str) -> str:
    return IDENTIFIER_SPLIT_RE.sub("_", value.lower()).strip("_")


def _ratio(samples: list[str], predicate) -> float:
    return sum(1 for sample in samples if predicate(sample)) / len(samples)


def _looks_like_email(value: str) -> bool:
    return EMAIL_RE.match(value) is not None


def _looks_like_phone(value: str) -> bool:
    digits = "".join(character for character in value if character.isdigit())
    return len(digits) >= 10 and any(character in value for character in "+()- ")


def _looks_like_street_address(value: str) -> bool:
    words = {
        IDENTIFIER_SPLIT_RE.sub("", word.lower())
        for word in value.split()
        if any(character.isalpha() for character in word)
    }
    return any(character.isdigit() for character in value) and bool(
        words & STREET_WORDS
    )


def _looks_like_name(value: str) -> bool:
    if any(character.isdigit() for character in value) or "@" in value:
        return False
    words = [word.strip(".,'-") for word in value.split()]
    if not 2 <= len(words) <= 4:
        return False
    return all(
        word and word[0].isupper() and any(char.isalpha() for char in word)
        for word in words
    )
