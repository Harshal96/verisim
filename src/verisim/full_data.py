from __future__ import annotations

import json
from functools import cache
from importlib.resources import files

from verisim.data import (
    COUNTRY_BY_LOCALE_REGION,
    LITE_COUNTRY_CODES,
    LITE_LOCALES,
    CountryData,
    LiteDataPack,
    NameData,
    _country_from_payload,
)
from verisim.models import PackMetadata

FULL_COUNTRY_CODES = (*LITE_COUNTRY_CODES, "ES")
FULL_LOCALES = (*LITE_LOCALES, ("es_ES", "latin"))
FULL_COUNTRY_BY_LOCALE_REGION = {**COUNTRY_BY_LOCALE_REGION, "ES": "ES"}


@cache
def _load_full_country(country_code: str) -> CountryData:
    resource = files("verisim.datasets.full.countries").joinpath(f"{country_code}.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    return _country_from_payload(payload)


@cache
def _load_full_locale(locale: str, script: str) -> NameData:
    resource = files("verisim.datasets.full.locales").joinpath(f"{locale}.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    if payload.get("locale") != locale:
        raise ValueError(f"locale file {resource.name!r} does not match {locale!r}")
    if payload.get("script") != script:
        raise ValueError(f"locale file {resource.name!r} does not support {script!r}")
    given = tuple(str(name) for name in payload["given"])
    family = tuple(str(name) for name in payload["family"])
    if not given or not family:
        raise ValueError(f"locale file {resource.name!r} must contain names")
    return NameData(given=given, family=family)


class FullDataPack(LiteDataPack):
    """Expanded data pack for broader locale and regional-address coverage."""

    metadata = PackMetadata(
        name="full",
        version="0.1.0",
        scope=(
            "Lite data plus additional locales, larger name pools, and regional "
            "address variants."
        ),
        provenance=(
            "Synthetic locale overlays authored for Verisim full-pack development.",
            "Postal/city/region relationships may be derived from public postal "
            "datasets with source attribution.",
            "Contacts and web domains use non-routable example.invalid-style "
            "outputs by default.",
        ),
        signed=False,
    )

    def __init__(self) -> None:
        super().__init__()
        full_countries = {
            country_code: _load_full_country(country_code)
            for country_code in FULL_COUNTRY_CODES
            if country_code not in LITE_COUNTRY_CODES
        }
        full_names = {
            (locale, script): _load_full_locale(locale, script)
            for locale, script in FULL_LOCALES
            if (locale, script) not in LITE_LOCALES
        }
        self.countries = {**self.countries, **full_countries}
        self.names = {**self.names, **full_names}

    def country_for_locale(self, locale: str) -> CountryData:
        region_code = locale.rsplit("_", 1)[-1].upper()
        country_code = FULL_COUNTRY_BY_LOCALE_REGION.get(region_code, "US")
        return self.countries[country_code]


__all__ = [
    "FULL_COUNTRY_BY_LOCALE_REGION",
    "FULL_COUNTRY_CODES",
    "FULL_LOCALES",
    "FullDataPack",
]
