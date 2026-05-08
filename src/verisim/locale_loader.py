from __future__ import annotations

import json
from functools import cache
from importlib.resources import files


@cache
def load_locale_names(
    locale: str, script: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    resource = files("verisim.datasets.locales").joinpath(f"{locale}.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    if payload.get("locale") != locale:
        raise ValueError(f"locale file {resource.name!r} does not match {locale!r}")
    if payload.get("script") != script:
        raise ValueError(f"locale file {resource.name!r} does not support {script!r}")
    given = tuple(payload["given"])
    family = tuple(payload["family"])
    if not given:
        raise ValueError(f"locale file {resource.name!r} has no given names")
    if not family:
        raise ValueError(f"locale file {resource.name!r} has no family names")
    if len(set(family)) != len(family):
        raise ValueError(
            f"locale file {resource.name!r} contains duplicate family names"
        )
    return given, family
