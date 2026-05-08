from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from importlib.resources import files
from os import PathLike
from random import Random
from zipfile import ZipFile

from verisim.locale_loader import load_locale_names
from verisim.models import Address, GeoPoint, PackMetadata


@dataclass(frozen=True)
class CityData:
    name: str
    postal_codes: tuple[str, ...]
    area_codes: tuple[str, ...]
    latitude: float
    longitude: float


@dataclass(frozen=True)
class RegionData:
    name: str
    code: str
    cities: tuple[CityData, ...]


@dataclass(frozen=True)
class CountryData:
    name: str
    code: str
    calling_code: str
    street_names: tuple[str, ...]
    street_suffixes: tuple[str, ...]
    regions: tuple[RegionData, ...]


@dataclass(frozen=True)
class NameData:
    given: tuple[str, ...]
    family: tuple[str, ...]


@dataclass(frozen=True)
class IndustryData:
    industry: str
    departments: tuple[str, ...]
    levels: tuple[str, ...]
    titles: tuple[str, ...]
    company_prefixes: tuple[str, ...]
    company_suffixes: tuple[str, ...]
    bio_templates: tuple[str, ...]


def _load_packaged_country(country_code: str) -> CountryData:
    resource = files("verisim.datasets.countries").joinpath(f"{country_code}.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    return _country_from_payload(payload)


def _country_from_payload(payload: dict[str, object]) -> CountryData:
    return CountryData(
        name=str(payload["name"]),
        code=str(payload["code"]),
        calling_code=str(payload["calling_code"]),
        street_names=tuple(str(name) for name in payload["street_names"]),
        street_suffixes=tuple(str(suffix) for suffix in payload["street_suffixes"]),
        regions=tuple(
            RegionData(
                name=str(region["name"]),
                code=str(region["code"]),
                cities=tuple(
                    CityData(
                        name=str(city["name"]),
                        postal_codes=tuple(
                            str(postal_code) for postal_code in city["postal_codes"]
                        ),
                        area_codes=tuple(
                            str(area_code) for area_code in city["area_codes"]
                        ),
                        latitude=float(city["latitude"]),
                        longitude=float(city["longitude"]),
                    )
                    for city in region["cities"]
                ),
            )
            for region in payload["regions"]
        ),
    )


def load_geonames_postal_countries(
    path: str | PathLike[str], country_codes: set[str] | None = None
) -> dict[str, CountryData]:
    region_rows = defaultdict(lambda: defaultdict(dict))
    with ZipFile(path) as archive:
        member = next(name for name in archive.namelist() if name.endswith(".txt"))
        with archive.open(member) as handle:
            for raw_line in handle:
                fields = raw_line.decode("utf-8").rstrip("\n").split("\t")
                if len(fields) < 12:
                    continue
                country_code = fields[0]
                if country_codes is not None and country_code not in country_codes:
                    continue
                postal_code = fields[1]
                city_name = fields[2]
                region_name = fields[3] or fields[4] or country_code
                region_code = fields[4] or region_name
                latitude = float(fields[9])
                longitude = float(fields[10])
                region_key = (region_name, region_code)
                city_data = region_rows[country_code][region_key].setdefault(
                    city_name,
                    {
                        "postal_codes": set(),
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                )
                city_data["postal_codes"].add(postal_code)

    countries: dict[str, CountryData] = {}
    for country_code, regions_by_key in region_rows.items():
        country_name, calling_code, street_names, street_suffixes = _country_defaults(
            country_code
        )
        regions = []
        for (region_name, region_code), cities_by_name in sorted(
            regions_by_key.items()
        ):
            cities = []
            for city_name, city_data in sorted(cities_by_name.items()):
                cities.append(
                    CityData(
                        name=city_name,
                        postal_codes=tuple(sorted(city_data["postal_codes"])),
                        area_codes=("555",),
                        latitude=city_data["latitude"],
                        longitude=city_data["longitude"],
                    )
                )
            regions.append(
                RegionData(name=region_name, code=region_code, cities=tuple(cities))
            )
        countries[country_code] = CountryData(
            name=country_name,
            code=country_code,
            calling_code=calling_code,
            street_names=street_names,
            street_suffixes=street_suffixes,
            regions=tuple(regions),
        )
    return countries


def _country_defaults(
    country_code: str,
) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    defaults = {
        "US": (
            "United States",
            "+1",
            ("Main", "Market", "Oak", "Pine", "Maple"),
            ("Street", "Avenue", "Road", "Lane", "Drive"),
        ),
        "IN": (
            "India",
            "+91",
            ("MG", "Nehru", "Park", "Station", "Lake"),
            ("Road", "Marg", "Nagar", "Street", "Lane"),
        ),
    }
    return defaults.get(
        country_code,
        (
            country_code,
            "",
            ("Main", "Market", "Central"),
            ("Street", "Road", "Avenue"),
        ),
    )


class LiteDataPack:
    """Small built-in data pack for coherent US data plus priority-country examples."""

    metadata = PackMetadata(
        name="lite",
        version="0.1.0",
        scope="US English plus priority-country sample data",
        provenance=(
            "Synthetic names, streets, companies, and contact handles authored "
            "for Verisim.",
            "Postal/city/state relationships are coarse public geographic facts.",
            "Contacts and web domains use non-routable example.invalid-style "
            "outputs by default.",
        ),
        signed=True,
    )

    def __init__(self) -> None:
        self.countries = {
            "US": _load_packaged_country("US"),
            "IN": _load_packaged_country("IN"),
        }
        en_us_given, en_us_family = load_locale_names("en_US", "latin")
        en_in_given, en_in_family = load_locale_names("en_IN", "latin")
        hi_in_given, hi_in_family = load_locale_names("hi_IN", "devanagari")
        self.names = {
            ("en_US", "latin"): NameData(
                given=en_us_given,
                family=en_us_family,
            ),
            ("en_IN", "latin"): NameData(
                given=en_in_given,
                family=en_in_family,
            ),
            ("hi_IN", "devanagari"): NameData(
                given=hi_in_given,
                family=hi_in_family,
            ),
        }
        self.industries = (
            IndustryData(
                industry="Data Infrastructure",
                departments=("Platform", "Data", "Engineering"),
                levels=("Associate", "Senior", "Lead", "Principal"),
                titles=(
                    "Data Engineer",
                    "Analytics Engineer",
                    "Data Scientist",
                    "Machine Learning Engineer",
                ),
                company_prefixes=(
                    "Northstar",
                    "Signal",
                    "Vector",
                    "Atlas",
                    "ClearLake",
                ),
                company_suffixes=("Data", "Systems", "Labs", "Analytics", "Works"),
                bio_templates=(
                    "{name} is a {title} at {company}, where they build "
                    "reliable data products for {industry}.",
                    "As a {title} at {company}, {name} turns messy operational "
                    "data into trusted {industry} systems.",
                ),
            ),
            IndustryData(
                industry="Healthcare Technology",
                departments=("Clinical Systems", "Product", "Security"),
                levels=("Specialist", "Senior", "Lead", "Director"),
                titles=(
                    "Product Manager",
                    "Security Analyst",
                    "Clinical Data Lead",
                    "Solutions Architect",
                ),
                company_prefixes=("Cedar", "Kindred", "Wellpath", "Nimbus", "Harbor"),
                company_suffixes=(
                    "Health",
                    "Care Systems",
                    "Medical Group",
                    "Therapeutics",
                    "Clinics",
                ),
                bio_templates=(
                    "{name} works as a {title} at {company}, improving "
                    "{industry} tools for care teams.",
                    "{name} is a {title} focused on practical {industry} "
                    "workflows at {company}.",
                ),
            ),
            IndustryData(
                industry="Financial Services",
                departments=("Risk", "Payments", "Operations"),
                levels=("Analyst", "Senior", "Lead", "Vice President"),
                titles=(
                    "Risk Analyst",
                    "Payments Engineer",
                    "Compliance Manager",
                    "Quantitative Analyst",
                ),
                company_prefixes=(
                    "Evergreen",
                    "Mercury",
                    "Summit",
                    "Oakline",
                    "Ledger",
                ),
                company_suffixes=(
                    "Capital",
                    "Payments",
                    "Advisors",
                    "Financial",
                    "Trust",
                ),
                bio_templates=(
                    "{name} is a {title} at {company}, working on dependable "
                    "{industry} products.",
                    "At {company}, {name} applies {industry} experience as a {title}.",
                ),
            ),
            IndustryData(
                industry="Climate Operations",
                departments=("Operations", "Field Systems", "Research"),
                levels=("Coordinator", "Senior", "Lead", "Principal"),
                titles=(
                    "Operations Manager",
                    "Field Systems Engineer",
                    "Research Analyst",
                    "Program Lead",
                ),
                company_prefixes=("Bluefield", "Terra", "Canopy", "Aster", "Greenline"),
                company_suffixes=("Energy", "Climate", "Renewables", "Works", "Grid"),
                bio_templates=(
                    "{name} is a {title} at {company}, coordinating practical "
                    "{industry} work.",
                    "{name} helps {company} make {industry} programs "
                    "measurable as a {title}.",
                ),
            ),
        )

    def country_for_locale(self, locale: str) -> CountryData:
        if locale.endswith("_IN"):
            return self.countries["IN"]
        return self.countries["US"]

    def names_for_locale(self, locale: str, script: str) -> NameData:
        if (locale, script) in self.names:
            return self.names[(locale, script)]
        for (candidate_locale, _), names in self.names.items():
            if candidate_locale == locale:
                return names
        return self.names[("en_US", "latin")]

    def street_names_for_country(self, country_code: str) -> tuple[str, ...]:
        return self.countries[country_code].street_names

    def choose_city(
        self, random: Random, country_code: str
    ) -> tuple[CountryData, RegionData, CityData]:
        country = self.countries[country_code]
        region = random.choice(country.regions)
        city = random.choice(region.cities)
        return country, region, city

    def postal_codes_for_city(
        self, country_code: str, region_code: str, city: str
    ) -> tuple[str, ...]:
        country = self.countries[country_code]
        for region in country.regions:
            if region.code != region_code:
                continue
            for city_data in region.cities:
                if city_data.name == city:
                    return city_data.postal_codes
        return ()

    def city_for_address(self, address: Address) -> CityData | None:
        country = self.countries.get(address.country_code)
        if not country:
            return None
        for region in country.regions:
            if region.code == address.region_code:
                for city in region.cities:
                    if (
                        city.name == address.city
                        and address.postal_code in city.postal_codes
                    ):
                        return city
        return None

    def make_address(
        self, random: Random, locale: str, country_code: str | None = None
    ) -> Address:
        country = (
            self.countries[country_code]
            if country_code
            else self.country_for_locale(locale)
        )
        _, region, city = self.choose_city(random, country.code)
        line1 = (
            f"{random.randint(10, 9999)} "
            f"{random.choice(self.street_names_for_country(country.code))} "
            f"{random.choice(country.street_suffixes)}"
        )
        return Address(
            line1=line1,
            city=city.name,
            region=region.name,
            region_code=region.code,
            postal_code=random.choice(city.postal_codes),
            country=country.name,
            country_code=country.code,
            geo=GeoPoint(latitude=city.latitude, longitude=city.longitude),
        )
