from __future__ import annotations

import re
import unicodedata
from random import Random


def ascii_slug(value: str, separator: str = "-") -> str:
    normalized = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    lowered = normalized.lower()
    slug = re.sub(r"[^a-z0-9]+", separator, lowered).strip(separator)
    return slug or "verisim"


def username_slug(value: str, separator: str = ".") -> str:
    normalized = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    slug = re.sub(r"[^a-z0-9._-]+", separator, normalized.lower()).strip("._-")
    slug = re.sub(r"[^a-z0-9._-]+", "", slug).strip("._-")
    return slug or "person"


def choose_weighted(random: Random, choices: list[tuple[object, int]]) -> object:
    total = sum(weight for _, weight in choices)
    pick = random.randint(1, total)
    seen = 0
    for value, weight in choices:
        seen += weight
        if pick <= seen:
            return value
    return choices[-1][0]
