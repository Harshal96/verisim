from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from os import PathLike
from random import Random
from zipfile import ZipFile

from verisim.locale_loader import load_locale_names
from verisim.models import Address, GeoPoint, PackMetadata

LITE_COUNTRY_CODES = ("US", "GB", "CA", "AU", "IN", "DE")
LITE_LOCALES = (
    ("en_US", "latin"),
    ("en_GB", "latin"),
    ("en_CA", "latin"),
    ("en_AU", "latin"),
    ("en_IN", "latin"),
    ("hi_IN", "devanagari"),
    ("de_DE", "latin"),
)
COUNTRY_BY_LOCALE_REGION = {
    "US": "US",
    "GB": "GB",
    "UK": "GB",
    "CA": "CA",
    "AU": "AU",
    "IN": "IN",
    "DE": "DE",
}


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


@cache
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
        members = [
            name
            for name in archive.namelist()
            if name.endswith(".txt") and name.rsplit("/", 1)[-1].lower() != "readme.txt"
        ]
        member = next(iter(members))
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
                        area_codes=_default_area_codes(country_code),
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


def _default_area_codes(country_code: str) -> tuple[str, ...]:
    return {
        "GB": ("20",),
        "AU": ("2",),
        "DE": ("30",),
    }.get(country_code, ("555",))


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
        "GB": (
            "United Kingdom",
            "+44",
            ("High", "Station", "Church", "Victoria", "Market"),
            ("Street", "Road", "Lane", "Close", "Way"),
        ),
        "CA": (
            "Canada",
            "+1",
            ("King", "Queen", "Maple", "Lake", "Cedar"),
            ("Street", "Avenue", "Road", "Drive", "Crescent"),
        ),
        "AU": (
            "Australia",
            "+61",
            ("George", "Collins", "King", "Queen", "Harbour"),
            ("Street", "Road", "Avenue", "Parade", "Drive"),
        ),
        "DE": (
            "Germany",
            "+49",
            ("Haupt", "Bahnhof", "Garten", "Markt", "Schiller"),
            ("Strasse", "Allee", "Weg", "Platz", "Ring"),
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
    """Small built-in data pack for coherent priority-country examples."""

    metadata = PackMetadata(
        name="lite",
        version="0.1.0",
        scope="US, UK, Canada, Australia, India, and Germany sample data",
        provenance=(
            "Synthetic names, streets, companies, and contact handles authored "
            "for Verisim.",
            "Postal/city/state relationships are derived from GeoNames postal "
            "code data under Creative Commons Attribution 4.0.",
            "UK full-code rows include Royal Mail copyright and database-right "
            "attribution through the GeoNames source archive.",
            "Contacts and web domains use non-routable example.invalid-style "
            "outputs by default.",
        ),
        signed=True,
    )

    def __init__(self) -> None:
        self.countries = {
            country_code: _load_packaged_country(country_code)
            for country_code in LITE_COUNTRY_CODES
        }
        self.names = {}
        for locale, script in LITE_LOCALES:
            given, family = load_locale_names(locale, script)
            self.names[(locale, script)] = NameData(given=given, family=family)
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
        region_code = locale.rsplit("_", 1)[-1].upper()
        country_code = COUNTRY_BY_LOCALE_REGION.get(region_code, "US")
        return self.countries[country_code]

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
