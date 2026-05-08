from __future__ import annotations

from dataclasses import dataclass
from random import Random

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
            "US": CountryData(
                name="United States",
                code="US",
                calling_code="+1",
                street_suffixes=(
                    "Street",
                    "Avenue",
                    "Road",
                    "Lane",
                    "Drive",
                    "Court",
                    "Place",
                    "Way",
                ),
                regions=(
                    RegionData(
                        "California",
                        "CA",
                        (
                            CityData(
                                "San Francisco",
                                ("94105", "94107", "94110"),
                                ("415", "628"),
                                37.789,
                                -122.394,
                            ),
                            CityData(
                                "Los Angeles",
                                ("90001", "90012", "90017"),
                                ("213", "323"),
                                34.052,
                                -118.244,
                            ),
                            CityData(
                                "San Diego",
                                ("92101", "92103", "92109"),
                                ("619", "858"),
                                32.715,
                                -117.161,
                            ),
                        ),
                    ),
                    RegionData(
                        "Texas",
                        "TX",
                        (
                            CityData(
                                "Austin",
                                ("78701", "78702", "78704"),
                                ("512", "737"),
                                30.267,
                                -97.743,
                            ),
                            CityData(
                                "Dallas",
                                ("75201", "75204", "75219"),
                                ("214", "469"),
                                32.776,
                                -96.797,
                            ),
                            CityData(
                                "Houston",
                                ("77002", "77006", "77019"),
                                ("713", "832"),
                                29.760,
                                -95.369,
                            ),
                        ),
                    ),
                    RegionData(
                        "New York",
                        "NY",
                        (
                            CityData(
                                "New York",
                                ("10001", "10003", "10011"),
                                ("212", "646"),
                                40.750,
                                -73.997,
                            ),
                            CityData(
                                "Buffalo",
                                ("14201", "14202", "14213"),
                                ("716",),
                                42.886,
                                -78.878,
                            ),
                        ),
                    ),
                    RegionData(
                        "Washington",
                        "WA",
                        (
                            CityData(
                                "Seattle",
                                ("98101", "98103", "98109"),
                                ("206", "425"),
                                47.606,
                                -122.332,
                            ),
                            CityData(
                                "Spokane",
                                ("99201", "99202", "99205"),
                                ("509",),
                                47.658,
                                -117.426,
                            ),
                        ),
                    ),
                    RegionData(
                        "Illinois",
                        "IL",
                        (
                            CityData(
                                "Chicago",
                                ("60601", "60607", "60614"),
                                ("312", "773"),
                                41.883,
                                -87.632,
                            ),
                        ),
                    ),
                    RegionData(
                        "Florida",
                        "FL",
                        (
                            CityData(
                                "Miami",
                                ("33101", "33130", "33139"),
                                ("305", "786"),
                                25.761,
                                -80.191,
                            ),
                            CityData(
                                "Orlando",
                                ("32801", "32803", "32819"),
                                ("407",),
                                28.538,
                                -81.379,
                            ),
                        ),
                    ),
                ),
            ),
            "IN": CountryData(
                name="India",
                code="IN",
                calling_code="+91",
                street_suffixes=("Road", "Marg", "Nagar", "Street", "Lane", "Colony"),
                regions=(
                    RegionData(
                        "Maharashtra",
                        "MH",
                        (
                            CityData(
                                "Mumbai",
                                ("400001", "400050", "400076"),
                                ("22",),
                                18.938,
                                72.835,
                            ),
                            CityData(
                                "Pune",
                                ("411001", "411004", "411045"),
                                ("20",),
                                18.520,
                                73.856,
                            ),
                        ),
                    ),
                    RegionData(
                        "Delhi",
                        "DL",
                        (
                            CityData(
                                "New Delhi",
                                ("110001", "110016", "110075"),
                                ("11",),
                                28.613,
                                77.209,
                            ),
                        ),
                    ),
                    RegionData(
                        "Karnataka",
                        "KA",
                        (
                            CityData(
                                "Bengaluru",
                                ("560001", "560034", "560100"),
                                ("80",),
                                12.971,
                                77.594,
                            ),
                        ),
                    ),
                    RegionData(
                        "Telangana",
                        "TS",
                        (
                            CityData(
                                "Hyderabad",
                                ("500001", "500032", "500081"),
                                ("40",),
                                17.385,
                                78.486,
                            ),
                        ),
                    ),
                ),
            ),
        }
        self.names = {
            ("en_US", "latin"): NameData(
                given=(
                    "Avery",
                    "Brooke",
                    "Cameron",
                    "Casey",
                    "Drew",
                    "Elliot",
                    "Harper",
                    "James",
                    "Jordan",
                    "Kelsey",
                    "Logan",
                    "Maya",
                    "Morgan",
                    "Parker",
                    "Quinn",
                    "Riley",
                    "Taylor",
                    "Sydney",
                    "Alex",
                    "Jamie",
                    "Nina",
                    "Miles",
                    "Leah",
                    "Owen",
                ),
                family=(
                    "Anderson",
                    "Bennett",
                    "Brooks",
                    "Carter",
                    "Chen",
                    "Diaz",
                    "Ellis",
                    "Foster",
                    "Garcia",
                    "Hayes",
                    "Johnson",
                    "Kim",
                    "Lee",
                    "Morgan",
                    "Nguyen",
                    "Patel",
                    "Reed",
                    "Rivera",
                    "Sullivan",
                    "Thomas",
                    "Walker",
                    "Ward",
                    "Young",
                    "Zhang",
                ),
            ),
            ("hi_IN", "latin"): NameData(
                given=(
                    "Aarav",
                    "Ananya",
                    "Isha",
                    "Kabir",
                    "Meera",
                    "Om",
                    "Prakash",
                    "Rakesh",
                ),
                family=(
                    "Agarwal",
                    "Gupta",
                    "Iyer",
                    "Kapoor",
                    "Khan",
                    "Mehta",
                    "Patel",
                    "Rao",
                    "Sharma",
                    "Singh",
                ),
            ),
        }
        self.street_names = (
            "Ash",
            "Beacon",
            "Birch",
            "Cedar",
            "Civic",
            "Elm",
            "Harbor",
            "Hillcrest",
            "Lake",
            "Maple",
            "Market",
            "Oak",
            "Pine",
            "River",
            "Summit",
            "Union",
            "Walnut",
            "Willow",
        )
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
        return self.names.get((locale, script), self.names[("en_US", "latin")])

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
            f"{random.randint(10, 9999)} {random.choice(self.street_names)} "
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
