from __future__ import annotations

import json
from functools import cache
from importlib.resources import files

SUPPORTED_LOCALE_SCRIPTS = frozenset(
    {
        ("en_US", "latin"),
        ("en_GB", "latin"),
        ("en_CA", "latin"),
        ("en_AU", "latin"),
        ("en_IN", "latin"),
        ("hi_IN", "devanagari"),
        ("de_DE", "latin"),
        ("es_MX", "latin"),
        ("ja_JP", "kanji"),
        ("fr_FR", "latin"),
        ("pt_BR", "latin"),
        ("zh_CN", "han"),
    }
)
SUPPORTED_LOCALES = frozenset(locale for locale, _ in SUPPORTED_LOCALE_SCRIPTS)


def validate_locale_script(locale: str, script: str) -> None:
    if locale not in SUPPORTED_LOCALES:
        raise ValueError(f"unsupported locale {locale!r}")
    if (locale, script) not in SUPPORTED_LOCALE_SCRIPTS:
        raise ValueError(f"unsupported locale/script {locale!r}/{script!r}")


@cache
def load_locale_names(
    locale: str, script: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    validate_locale_script(locale, script)
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
