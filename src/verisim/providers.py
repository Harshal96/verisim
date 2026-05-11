from __future__ import annotations

from datetime import date
from random import Random

from verisim.constants import (
    DEFAULT_EMAIL_PATTERN,
    DEFAULT_REVENUE_PER_EMPLOYEE,
    DEPARTMENT_ADDITIONS_BY_SIZE_BAND,
    DEPARTMENT_LIMITS_BY_SIZE_BAND,
    EMAIL_PATTERNS,
    FUNDING_STAGES_BY_SIZE_BAND,
    INDUSTRY_EXECUTIVE_TITLES,
    LEGAL_ENTITY_TYPES_BY_COUNTRY,
    MIN_REVENUE,
    REVENUE_MULTIPLIERS,
    REVENUE_PER_EMPLOYEE,
    REVENUE_ROUNDING_BUCKET,
    SIZE_BAND_AGE_RANGES,
    SIZE_BAND_CHOICES_BY_MAX_AGE,
    SIZE_BAND_CHOICES_FOR_OLDER_COMPANIES,
    SIZE_BAND_EMPLOYEE_RANGES,
)
from verisim.context import GenerationState
from verisim.data import IndustryData, NameData
from verisim.models import (
    Company,
    CompanyRecord,
    Contact,
    IncorporationJurisdiction,
    Job,
    LeadershipMember,
    Person,
    PersonRecord,
    PhoneNumber,
    PriceRange,
    ProductPlan,
    ProductRecord,
    RevenueRange,
    SocialAccount,
    Socials,
    Website,
)
from verisim.types import EmailPattern, SizeBand
from verisim.utils import ascii_slug, username_slug


def _industry_by_name(state: GenerationState, industry_name: str) -> IndustryData:
    for industry in state.data.industries:
        if industry.industry == industry_name:
            return industry
    return state.data.industries[0]


def _personal_domain(username: str) -> str:
    return f"{username.replace('_', '-')}.example.invalid"


def _platform_url(platform: str, handle: str) -> str:
    if platform == "x":
        return f"https://x.com/{handle}"
    if platform == "instagram":
        return f"https://instagram.com/{handle}"
    if platform == "linkedin":
        return f"https://linkedin.com/in/{handle}"
    return f"https://github.com/{handle}"


class AddressProvider:
    provides = ("address",)
    requires: tuple[str, ...] = ()

    def generate(self, state: GenerationState) -> dict[str, object]:
        return {"address": state.data.make_address(state.random, state.locale)}


class PersonProvider:
    provides = ("person",)
    requires: tuple[str, ...] = ()

    def generate(self, state: GenerationState) -> dict[str, object]:
        names = state.data.names_for_locale(state.locale, state.script)
        given_name, family_name = self._unique_name(state, names)
        name = f"{given_name} {family_name}"
        birthdate = self._birthdate(state.random)
        username = self._username(state, given_name, family_name, birthdate.year)
        return {
            "person": Person(
                given_name=given_name,
                family_name=family_name,
                name=name,
                username=username,
                birthdate=birthdate.isoformat(),
                locale=state.locale,
            )
        }

    def _birthdate(self, random: Random) -> date:
        year = random.randint(1964, 2004)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        return date(year, month, day)

    def _unique_name(self, state: GenerationState, names: NameData) -> tuple[str, str]:
        if len(names.family) >= 10_000:
            return state.random.choice(names.given), self._unique_family_name(
                state, names.family
            )
        return self._unique_full_name(state, names)

    def _unique_family_name(
        self, state: GenerationState, family_names: tuple[str, ...]
    ) -> str:
        start = state.random.randrange(len(family_names))

        def candidate(attempt: int) -> str:
            return family_names[(start + attempt) % len(family_names)]

        return str(
            state.registry.unique(
                "person_family_name", candidate, max_attempts=len(family_names)
            )
        )

    def _unique_full_name(
        self, state: GenerationState, names: NameData
    ) -> tuple[str, str]:
        family_count = len(names.family)
        total_names = len(names.given) * family_count
        start = state.random.randrange(total_names)

        def candidate(attempt: int) -> tuple[str, str]:
            index = (start + attempt) % total_names
            given_index, family_index = divmod(index, family_count)
            return names.given[given_index], names.family[family_index]

        given_name, family_name = state.registry.unique(
            "person_name", candidate, max_attempts=total_names
        )
        return str(given_name), str(family_name)

    def _username(
        self, state: GenerationState, given_name: str, family_name: str, birth_year: int
    ) -> str:
        first = username_slug(given_name)
        last = username_slug(family_name)
        patterns = (
            f"{first}.{last}",
            f"{first}{last}",
            f"{first}_{last}",
            f"{first[0]}{last}",
            f"{first}{birth_year % 100:02d}",
            f"{last}.{first}",
        )

        def candidate(attempt: int) -> str:
            if attempt < len(patterns):
                return patterns[attempt]
            return f"{patterns[attempt % len(patterns)]}{attempt}"

        return str(state.registry.unique("username", candidate))


class IndustryProvider:
    provides = ("industry_data",)
    requires: tuple[str, ...] = ()

    def generate(self, state: GenerationState) -> dict[str, object]:
        requested = state.facts.get("industry")
        if isinstance(requested, str):
            return {"industry_data": _industry_by_name(state, requested)}
        return {"industry_data": state.random.choice(state.data.industries)}


class CompanyProvider:
    provides = ("company",)
    requires = ("industry_data",)

    def generate(self, state: GenerationState) -> dict[str, object]:
        industry = state.facts["industry_data"]
        assert isinstance(industry, IndustryData)
        name = self._company_name(state, industry)
        slug = ascii_slug(name)
        domain = f"{slug}.example.invalid"
        company = Company(
            id=state.registry.uuid("company"),
            name=name,
            industry=industry.industry,
            domain=domain,
            website=Website.from_host(domain),
            address=state.data.make_address(state.random, state.locale),
        )
        return {"company": company}

    def _company_name(self, state: GenerationState, industry: IndustryData) -> str:
        def candidate(attempt: int) -> str:
            prefix = state.random.choice(industry.company_prefixes)
            suffix = state.random.choice(industry.company_suffixes)
            base = f"{prefix} {suffix}"
            return base if attempt == 0 else f"{base} {attempt + 1}"

        return str(state.registry.unique("company_name", candidate))


class CompanyRecordProvider(CompanyProvider):
    provides = ("company_record",)
    requires = ("industry_data",)

    def generate(self, state: GenerationState) -> dict[str, object]:
        industry = state.facts["industry_data"]
        assert isinstance(industry, IndustryData)

        requested_size_band = self._requested_size_band(state)
        founded_year = self._founded_year(state, requested_size_band)
        size_band = self._size_band(state, founded_year, requested_size_band)
        employee_count = self._employee_count(state, size_band)
        headquarters = state.data.make_address(state.random, state.locale)
        legal_entity_type = self._legal_entity_type(state, headquarters.country_code)
        name = self._company_name(state, industry)
        slug = ascii_slug(name)
        domain = f"{slug}.example.invalid"
        departments = self._departments(industry, size_band)

        record = CompanyRecord(
            id=state.registry.uuid("company"),
            name=name,
            legal_entity_type=legal_entity_type,
            founded_year=founded_year,
            industry=industry.industry,
            size_band=size_band,
            employee_count=employee_count,
            revenue_range=self._revenue_range(industry, size_band, employee_count),
            funding_stage=self._funding_stage(state, size_band, founded_year),
            headquarters=headquarters,
            incorporated_in=self._incorporated_in(
                state, legal_entity_type, headquarters
            ),
            domain=domain,
            website=Website.from_host(domain),
            email_pattern=state.random.choice(EMAIL_PATTERNS),
            linkedin_slug=slug,
            departments=departments,
            leadership=self._leadership(state, industry, size_band, departments),
        )
        return {
            "company_record": record,
            "company": record.as_company(),
            "industry": record.industry,
            "size_band": record.size_band,
        }

    def _requested_size_band(self, state: GenerationState) -> SizeBand | None:
        requested = state.facts.get("size_band")
        if isinstance(requested, str) and requested in SIZE_BAND_EMPLOYEE_RANGES:
            return requested  # type: ignore[return-value]
        return None

    def _founded_year(
        self, state: GenerationState, requested_size_band: SizeBand | None
    ) -> int:
        requested = state.facts.get("founded_year")
        if isinstance(requested, int):
            return requested

        current_year = date.today().year
        if requested_size_band is None:
            return current_year - state.random.randint(0, 35)

        low, high = SIZE_BAND_AGE_RANGES[requested_size_band]
        return current_year - state.random.randint(low, high)

    def _size_band(
        self,
        state: GenerationState,
        founded_year: int,
        requested_size_band: SizeBand | None,
    ) -> SizeBand:
        if requested_size_band is not None:
            return requested_size_band

        age = max(0, date.today().year - founded_year)
        for max_age, choices in SIZE_BAND_CHOICES_BY_MAX_AGE:
            if age <= max_age:
                return state.random.choice(choices)
        return state.random.choice(SIZE_BAND_CHOICES_FOR_OLDER_COMPANIES)

    def _employee_count(self, state: GenerationState, size_band: SizeBand) -> int:
        low, high = SIZE_BAND_EMPLOYEE_RANGES[size_band]
        return state.random.randint(low, high)

    def _legal_entity_type(self, state: GenerationState, country_code: str) -> str:
        entity_types = LEGAL_ENTITY_TYPES_BY_COUNTRY.get(
            country_code, LEGAL_ENTITY_TYPES_BY_COUNTRY["US"]
        )
        return state.random.choice(entity_types)

    def _incorporated_in(
        self, state: GenerationState, legal_entity_type: str, headquarters: object
    ) -> IncorporationJurisdiction:
        country_code = getattr(headquarters, "country_code")
        region = getattr(headquarters, "region")
        region_code = getattr(headquarters, "region_code")
        country = getattr(headquarters, "country")

        if (
            country_code == "US"
            and legal_entity_type in {"Inc.", "Corporation"}
            and state.random.random() < 0.65
        ):
            return IncorporationJurisdiction(
                country="United States",
                country_code="US",
                region="Delaware",
                region_code="DE",
            )

        return IncorporationJurisdiction(
            country=country,
            country_code=country_code,
            region=region,
            region_code=region_code,
        )

    def _revenue_range(
        self, industry: IndustryData, size_band: SizeBand, employee_count: int
    ) -> RevenueRange:
        revenue_per_employee = REVENUE_PER_EMPLOYEE.get(
            industry.industry, DEFAULT_REVENUE_PER_EMPLOYEE
        )
        low_multiplier, high_multiplier = REVENUE_MULTIPLIERS[size_band]
        low = self._round_revenue(
            int(employee_count * revenue_per_employee * low_multiplier)
        )
        high = self._round_revenue(
            int(employee_count * revenue_per_employee * high_multiplier), up=True
        )
        return RevenueRange(
            annual_min_usd=low,
            annual_max_usd=max(high, low + REVENUE_ROUNDING_BUCKET),
        )

    def _round_revenue(self, value: int, up: bool = False) -> int:
        if up:
            rounded = (
                (value + REVENUE_ROUNDING_BUCKET - 1) // REVENUE_ROUNDING_BUCKET
            ) * REVENUE_ROUNDING_BUCKET
        else:
            rounded = (value // REVENUE_ROUNDING_BUCKET) * REVENUE_ROUNDING_BUCKET
        return max(MIN_REVENUE, rounded)

    def _funding_stage(
        self, state: GenerationState, size_band: SizeBand, founded_year: int
    ) -> str:
        age = max(0, date.today().year - founded_year)
        stages = FUNDING_STAGES_BY_SIZE_BAND[size_band]
        if age < 8:
            stages = tuple(stage for stage in stages if stage != "IPO")
        return state.random.choice(stages)

    def _departments(self, industry: IndustryData, size_band: SizeBand) -> list[str]:
        additions = DEPARTMENT_ADDITIONS_BY_SIZE_BAND[size_band]
        ordered = list(industry.departments) + list(additions)
        departments = list(dict.fromkeys(ordered))
        return departments[: DEPARTMENT_LIMITS_BY_SIZE_BAND[size_band]]

    def _leadership(
        self,
        state: GenerationState,
        industry: IndustryData,
        size_band: SizeBand,
        departments: list[str],
    ) -> list[LeadershipMember]:
        titles = self._leadership_titles(industry, size_band, departments)
        leader_provider = PersonProvider()
        leaders = []
        for title, department in titles:
            person = leader_provider.generate(state)["person"]
            assert isinstance(person, Person)
            leaders.append(
                LeadershipMember(person=person, title=title, department=department)
            )
        return leaders

    def _leadership_titles(
        self, industry: IndustryData, size_band: SizeBand, departments: list[str]
    ) -> list[tuple[str, str | None]]:
        industry_executive = INDUSTRY_EXECUTIVE_TITLES.get(
            industry.industry, f"Head of {departments[0]}"
        )

        if size_band == "seed":
            return [("Founder & CEO", "Founding Team")]
        if size_band == "startup":
            return [
                ("Founder & CEO", None),
                ("CTO", self._department_or_default(departments, "Engineering")),
                (
                    "Head of Product",
                    self._department_or_default(departments, "Product"),
                ),
            ]
        if size_band == "SMB":
            return [
                ("CEO", None),
                (
                    "VP Operations",
                    self._department_or_default(departments, "Operations"),
                ),
                ("Head of Sales", self._department_or_default(departments, "Sales")),
                (industry_executive, departments[0]),
            ]
        if size_band == "mid-market":
            return [
                ("CEO", None),
                ("CFO", self._department_or_default(departments, "Finance")),
                ("CTO", self._department_or_default(departments, "Engineering")),
                ("VP Sales", self._department_or_default(departments, "Sales")),
                (industry_executive, departments[0]),
            ]
        return [
            ("CEO", None),
            ("CFO", self._department_or_default(departments, "Finance")),
            ("COO", self._department_or_default(departments, "Operations")),
            ("CTO", self._department_or_default(departments, "Engineering")),
            ("CHRO", self._department_or_default(departments, "People")),
            (
                "General Counsel",
                self._department_or_default(departments, "Corporate Affairs"),
            ),
            (industry_executive, departments[0]),
        ]

    def _department_or_default(self, departments: list[str], preferred: str) -> str:
        return preferred if preferred in departments else departments[0]


class JobProvider:
    provides = ("job",)
    requires = ("company",)

    def generate(self, state: GenerationState) -> dict[str, object]:
        company = state.facts["company"]
        assert isinstance(company, Company)
        company_record = state.facts.get("company_record")
        industry = _industry_by_name(state, company.industry)
        departments = (
            company_record.departments
            if isinstance(company_record, CompanyRecord)
            else industry.departments
        )
        return {
            "job": Job(
                title=state.random.choice(industry.titles),
                industry=company.industry,
                department=self._department(state, company, departments),
                level=state.random.choice(industry.levels),
                company_id=company.id,
            )
        }

    def _department(
        self,
        state: GenerationState,
        company: Company,
        departments: tuple[str, ...] | list[str],
    ) -> str:
        if "company_record" not in state.facts:
            return state.random.choice(tuple(departments))
        index = state.registry.next_index(f"company-department:{company.id}")
        return departments[index % len(departments)]


class ContactProvider:
    provides = ("contact",)
    requires = ("person", "address")

    def generate(self, state: GenerationState) -> dict[str, object]:
        person = state.facts["person"]
        address = state.facts["address"]
        assert isinstance(person, Person)
        country_code = getattr(address, "country_code")
        email = self._email(state, person)
        phone = self._phone(state, country_code, address)
        return {"contact": Contact(email=email, phone=phone)}

    def _email(self, state: GenerationState, person: Person) -> str:
        company_record = state.facts.get("company_record")
        company = state.facts.get("company")
        if isinstance(company_record, CompanyRecord):
            return self._company_email(
                state, person, company_record.domain, company_record.email_pattern
            )
        if isinstance(company, Company):
            return self._company_email(
                state, person, company.domain, DEFAULT_EMAIL_PATTERN
            )

        city_part = "mail"
        address = state.facts.get("address")
        if address is not None:
            city_part = ascii_slug(getattr(address, "city", "mail"))
        base = username_slug(person.username, separator=".")

        def candidate(attempt: int) -> str:
            local = base if attempt == 0 else f"{base}.{attempt + 1}"
            return f"{local}@{city_part}.example.invalid"

        return str(state.registry.unique("email", candidate))

    def _company_email(
        self,
        state: GenerationState,
        person: Person,
        domain: str,
        pattern: EmailPattern,
    ) -> str:
        first = username_slug(person.given_name, separator="")
        last = username_slug(person.family_name, separator="")
        if pattern == "flast":
            base = f"{first[0]}{last}"
        elif pattern == "first_last":
            base = f"{first}_{last}"
        elif pattern == "first":
            base = first
        else:
            base = f"{first}.{last}"

        def candidate(attempt: int) -> str:
            local = base if attempt == 0 else f"{base}.{attempt + 1}"
            return f"{local}@{domain}"

        return str(state.registry.unique("email", candidate))

    def _phone(
        self, state: GenerationState, country_code: str, address: object
    ) -> PhoneNumber:
        base = state.registry.next_index(f"phone-sequence:{country_code}")
        city = (
            state.data.city_for_address(address)
            if hasattr(address, "postal_code")
            else None
        )

        def area_code(fallback: str) -> str:
            return (
                state.random.choice(city.area_codes) if city is not None else fallback
            )

        def candidate(attempt: int) -> PhoneNumber:
            sequence = base + attempt
            if country_code == "IN":
                subscriber = f"{9000000000 + (sequence % 999999):010d}"
                return PhoneNumber(
                    e164=f"+91{subscriber}",
                    national=f"{subscriber[:5]} {subscriber[5:]}",
                    country_code="IN",
                    country_calling_code="+91",
                )
            if country_code == "GB":
                area = area_code("20")
                subscriber = f"{79460000 + (sequence % 10_000):08d}"
                return PhoneNumber(
                    e164=f"+44{area}{subscriber}",
                    national=f"0{area} {subscriber[:4]} {subscriber[4:]}",
                    country_code="GB",
                    country_calling_code="+44",
                )
            if country_code == "AU":
                area = area_code("2")
                subscriber = f"{55550000 + (sequence % 10_000):08d}"
                return PhoneNumber(
                    e164=f"+61{area}{subscriber}",
                    national=f"0{area} {subscriber[:4]} {subscriber[4:]}",
                    country_code="AU",
                    country_calling_code="+61",
                )
            if country_code == "DE":
                area = area_code("30")
                subscriber = f"{5550000 + (sequence % 10_000):07d}"
                return PhoneNumber(
                    e164=f"+49{area}{subscriber}",
                    national=f"0{area} {subscriber[:3]} {subscriber[3:]}",
                    country_code="DE",
                    country_calling_code="+49",
                )
            if country_code == "MX":
                area = area_code("55")
                subscriber = f"{55550000 + (sequence % 10_000):08d}"
                return PhoneNumber(
                    e164=f"+52{area}{subscriber}",
                    national=f"{area} {subscriber[:4]} {subscriber[4:]}",
                    country_code="MX",
                    country_calling_code="+52",
                )
            if country_code == "JP":
                area = area_code("3")
                subscriber = f"{55550000 + (sequence % 10_000):08d}"
                return PhoneNumber(
                    e164=f"+81{area}{subscriber}",
                    national=f"0{area} {subscriber[:4]} {subscriber[4:]}",
                    country_code="JP",
                    country_calling_code="+81",
                )
            if country_code == "FR":
                area = area_code("1")
                subscriber = f"{55550199 + (sequence % 10_000):08d}"
                return PhoneNumber(
                    e164=f"+33{area}{subscriber}",
                    national=(
                        f"0{area} {subscriber[:2]} {subscriber[2:4]} "
                        f"{subscriber[4:6]} {subscriber[6:]}"
                    ),
                    country_code="FR",
                    country_calling_code="+33",
                )
            if country_code == "BR":
                area = area_code("11")
                subscriber = f"{55550000 + (sequence % 10_000):08d}"
                return PhoneNumber(
                    e164=f"+55{area}{subscriber}",
                    national=f"({area}) {subscriber[:4]}-{subscriber[4:]}",
                    country_code="BR",
                    country_calling_code="+55",
                )
            if country_code == "CN":
                area = area_code("10")
                subscriber = f"{55550000 + (sequence % 10_000):08d}"
                return PhoneNumber(
                    e164=f"+86{area}{subscriber}",
                    national=f"0{area} {subscriber[:4]} {subscriber[4:]}",
                    country_code="CN",
                    country_calling_code="+86",
                )

            area = area_code("555")
            line = sequence % 10_000
            resolved_country_code = "CA" if country_code == "CA" else "US"
            return PhoneNumber(
                e164=f"+1{area}555{line:04d}",
                national=f"({area}) 555-{line:04d}",
                country_code=resolved_country_code,
                country_calling_code="+1",
            )

        phone = state.registry.unique("phone", candidate)
        assert isinstance(phone, PhoneNumber)
        return phone


class SocialsProvider:
    provides = ("socials",)
    requires = ("person", "job", "company")

    def generate(self, state: GenerationState) -> dict[str, object]:
        person = state.facts["person"]
        job = state.facts["job"]
        company = state.facts["company"]
        assert isinstance(person, Person)
        assert isinstance(job, Job)
        assert isinstance(company, Company)

        first = username_slug(person.given_name)
        last = username_slug(person.family_name)
        company_hint = username_slug(company.name.split()[0])
        job_hint = username_slug(job.title.split()[0])
        handles = {
            "x": self._unique_handle(
                state, "x", (person.username, f"{first}{last}", f"{first}_{job_hint}")
            ),
            "instagram": self._unique_handle(
                state,
                "instagram",
                (f"{first}.{last}", f"{first}_{last}", f"{first}.{company_hint}"),
            ),
            "linkedin": self._unique_handle(
                state,
                "linkedin",
                (
                    f"{first}-{last}",
                    f"{first}-{last}-{company_hint}",
                    f"{first}-{last}-{state.random.randint(100, 999)}",
                ),
            ),
            "github": self._unique_handle(
                state,
                "github",
                (f"{last}{first[0]}", f"{first}-{job_hint}", f"{first}{last}-dev"),
            ),
        }
        return {
            "socials": Socials(
                x=SocialAccount(
                    platform="x",
                    handle=handles["x"],
                    url=_platform_url("x", handles["x"]),
                ),
                instagram=SocialAccount(
                    platform="instagram",
                    handle=handles["instagram"],
                    url=_platform_url("instagram", handles["instagram"]),
                ),
                linkedin=SocialAccount(
                    platform="linkedin",
                    handle=handles["linkedin"],
                    url=_platform_url("linkedin", handles["linkedin"]),
                ),
                github=SocialAccount(
                    platform="github",
                    handle=handles["github"],
                    url=_platform_url("github", handles["github"]),
                ),
            )
        }

    def _unique_handle(
        self, state: GenerationState, platform: str, candidates: tuple[str, ...]
    ) -> str:
        def candidate(attempt: int) -> str:
            base = username_slug(
                candidates[attempt % len(candidates)],
                separator="-" if platform == "linkedin" else ".",
            )
            return base if attempt < len(candidates) else f"{base}{attempt}"

        return str(state.registry.unique(f"social:{platform}", candidate))


class WebsiteProvider:
    provides = ("website",)
    requires = ("person",)

    def generate(self, state: GenerationState) -> dict[str, object]:
        person = state.facts["person"]
        assert isinstance(person, Person)
        return {"website": Website.from_host(_personal_domain(person.username))}


class AvatarProvider:
    provides = ("avatar",)
    requires = ("person",)

    def generate(self, state: GenerationState) -> dict[str, object]:
        person = state.facts["person"]
        assert isinstance(person, Person)
        return {"avatar": f"https://avatars.example.invalid/{person.username}.png"}


class BioProvider:
    provides = ("bio",)
    requires = ("person", "job", "company")

    def generate(self, state: GenerationState) -> dict[str, object]:
        person = state.facts["person"]
        job = state.facts["job"]
        company = state.facts["company"]
        assert isinstance(person, Person)
        assert isinstance(job, Job)
        assert isinstance(company, Company)
        industry = _industry_by_name(state, company.industry)
        template = state.random.choice(industry.bio_templates)
        return {
            "bio": template.format(
                name=person.name,
                title=job.title,
                company=company.name,
                industry=company.industry,
            )
        }


class ProductRecordProvider:
    provides = ("product_record", "product")
    requires = ("company", "industry_data")

    def generate(self, state: GenerationState) -> dict[str, object]:
        company = state.facts["company"]
        industry = state.facts["industry_data"]
        assert isinstance(company, Company)
        assert isinstance(industry, IndustryData)

        company_record = state.facts.get("company_record")
        departments = self._departments(company_record, industry)
        target_size_band = self._target_size_band(state, company_record)
        category = self._category(state, company, industry)
        name = self._name(state, company, industry, category)
        slug = self._slug(state, company, name)
        launch_year = self._launch_year(state, company_record)
        product_type = self._product_type(state, industry)
        pricing_model = self._pricing_model(state, product_type)
        features = self._features(state, industry, target_size_band)
        target_departments = self._target_departments(
            state, departments, target_size_band
        )
        owner_department = state.random.choice(target_departments)
        website = Website.from_host(company.domain, f"/products/{slug}")

        record = ProductRecord(
            id=state.registry.uuid("product"),
            company=company,
            name=name,
            slug=slug,
            product_type=product_type,
            lifecycle_stage=self._lifecycle_stage(state, launch_year),
            launch_year=launch_year,
            industry=company.industry,
            category=category,
            owner_department=owner_department,
            target_departments=target_departments,
            target_size_band=target_size_band,
            description=self._description(
                state, industry, company, name, category, target_departments
            ),
            website=website,
            pricing_model=pricing_model,
            features=features,
            plans=self._plans(
                state,
                company,
                slug,
                pricing_model,
                target_size_band,
                target_departments,
                features,
            ),
        )
        return {"product_record": record, "product": record.as_product()}

    def _departments(self, company_record: object, industry: IndustryData) -> list[str]:
        if isinstance(company_record, CompanyRecord):
            return list(company_record.departments)
        return list(industry.departments)

    def _target_size_band(
        self, state: GenerationState, company_record: object
    ) -> SizeBand:
        if isinstance(company_record, CompanyRecord):
            return company_record.size_band
        requested = state.facts.get("size_band")
        if isinstance(requested, str) and requested in SIZE_BAND_EMPLOYEE_RANGES:
            return requested  # type: ignore[return-value]
        return state.random.choice(tuple(SIZE_BAND_EMPLOYEE_RANGES))

    def _categories(self, industry: IndustryData) -> tuple[str, ...]:
        return industry.product_categories or ("Operations Platform",)

    def _category(
        self, state: GenerationState, company: Company, industry: IndustryData
    ) -> str:
        categories = self._categories(industry)
        index = state.registry.next_index(f"product-category:{company.id}")
        return categories[index % len(categories)]

    def _name(
        self,
        state: GenerationState,
        company: Company,
        industry: IndustryData,
        category: str,
    ) -> str:
        templates = industry.product_name_templates
        if not templates:
            templates = (
                "{company} {modifier} {noun}",
                "{company} {category} {noun}",
            )
        modifiers = industry.product_modifiers or (
            "Core",
            "Signal",
            "Nexus",
            "Atlas",
            "Beacon",
            "Vertex",
            "Summit",
            "Relay",
        )
        nouns = industry.product_nouns or (
            "Cloud",
            "Hub",
            "Engine",
            "Console",
            "Platform",
            "Desk",
            "Grid",
            "Works",
        )
        company_root = company.name.split()[0]
        start = state.registry.next_index(f"product-name-sequence:{company.id}")
        category_name = category.replace("/", " ")

        def candidate(attempt: int) -> str:
            index = start + attempt
            template = templates[index % len(templates)]
            modifier = modifiers[(index // len(templates)) % len(modifiers)]
            noun = nouns[(index // (len(templates) * len(modifiers))) % len(nouns)]
            cycle = index // (len(templates) * len(modifiers) * len(nouns))
            name = template.format(
                company=company_root,
                category=category_name,
                modifier=modifier,
                noun=noun,
            )
            return name if cycle == 0 else f"{name} {cycle + 1}"

        return str(state.registry.unique(f"product-name:{company.id}", candidate))

    def _slug(self, state: GenerationState, company: Company, name: str) -> str:
        base = ascii_slug(name)

        def candidate(attempt: int) -> str:
            return base if attempt == 0 else f"{base}-{attempt + 1}"

        return str(state.registry.unique(f"product-slug:{company.id}", candidate))

    def _launch_year(self, state: GenerationState, company_record: object) -> int:
        current_year = date.today().year
        if isinstance(company_record, CompanyRecord):
            low = min(company_record.founded_year, current_year)
        else:
            low = current_year - state.random.randint(0, 6)
        return state.random.randint(max(1800, low), current_year)

    def _product_type(self, state: GenerationState, industry: IndustryData) -> str:
        choices_by_industry = {
            "Data Infrastructure": ("platform", "data_product", "software"),
            "Healthcare Technology": ("software", "managed_service", "platform"),
            "Financial Services": ("financial_product", "platform", "software"),
            "Climate Operations": ("program", "managed_service", "platform"),
        }
        choices = choices_by_industry.get(
            industry.industry, ("software", "platform", "managed_service")
        )
        return state.random.choice(choices)

    def _pricing_model(self, state: GenerationState, product_type: str) -> str:
        choices_by_type = {
            "software": ("subscription", "usage_based", "contract"),
            "platform": ("subscription", "usage_based", "contract"),
            "data_product": ("subscription", "usage_based", "contract"),
            "managed_service": ("contract", "project", "subscription"),
            "program": ("project", "contract", "subscription"),
            "financial_product": ("transaction", "contract", "subscription"),
        }
        return state.random.choice(choices_by_type[product_type])

    def _features(
        self, state: GenerationState, industry: IndustryData, size_band: SizeBand
    ) -> list[str]:
        features = industry.product_features or (
            "workflow automation",
            "role-based dashboards",
            "managed reporting",
            "secure collaboration",
            "administrative controls",
        )
        count = 4 if size_band in {"seed", "startup"} else 5
        return self._rotating_subset(state, list(features), min(count, len(features)))

    def _target_departments(
        self, state: GenerationState, departments: list[str], size_band: SizeBand
    ) -> list[str]:
        count = 2 if size_band in {"seed", "startup"} else 3
        return self._rotating_subset(state, departments, min(count, len(departments)))

    def _rotating_subset(
        self, state: GenerationState, values: list[str], count: int
    ) -> list[str]:
        start = state.random.randrange(len(values))
        return [values[(start + index) % len(values)] for index in range(count)]

    def _lifecycle_stage(self, state: GenerationState, launch_year: int) -> str:
        age = max(0, date.today().year - launch_year)
        if age <= 1:
            return state.random.choice(("beta", "launched"))
        if age <= 3:
            return state.random.choice(("launched", "growth"))
        if age <= 8:
            return state.random.choice(("growth", "mature"))
        return "mature"

    def _description(
        self,
        state: GenerationState,
        industry: IndustryData,
        company: Company,
        product_name: str,
        category: str,
        target_departments: list[str],
    ) -> str:
        templates = industry.product_description_templates or (
            "{product} helps {target_departments} teams run dependable "
            "{category} workflows.",
        )
        return state.random.choice(templates).format(
            product=product_name,
            company=company.name,
            industry=company.industry,
            category=category,
            target_departments=", ".join(target_departments),
        )

    def _plans(
        self,
        state: GenerationState,
        company: Company,
        slug: str,
        pricing_model: str,
        size_band: SizeBand,
        target_departments: list[str],
        features: list[str],
    ) -> list[ProductPlan]:
        plan_names = ("Starter", "Growth", "Enterprise")
        plan_count = 2 if size_band in {"seed", "startup"} else 3
        billing_interval = self._billing_interval(state, pricing_model)
        return [
            ProductPlan(
                sku=self._sku(state, company, slug, plan_name),
                name=plan_name,
                description=(
                    f"{plan_name} plan for "
                    f"{', '.join(target_departments).lower()} teams."
                ),
                billing_interval=billing_interval,
                price_range=self._price_range(size_band, billing_interval, index),
                included_features=self._included_features(features, index),
            )
            for index, plan_name in enumerate(plan_names[:plan_count])
        ]

    def _billing_interval(self, state: GenerationState, pricing_model: str) -> str:
        intervals_by_model = {
            "subscription": ("monthly", "annual"),
            "usage_based": ("usage", "monthly"),
            "contract": ("annual",),
            "transaction": ("usage",),
            "project": ("one_time",),
        }
        return state.random.choice(intervals_by_model[pricing_model])

    def _price_range(
        self, size_band: SizeBand, billing_interval: str, plan_index: int
    ) -> PriceRange:
        base_by_size = {
            "seed": (49, 199),
            "startup": (199, 799),
            "SMB": (799, 2499),
            "mid-market": (2500, 9000),
            "enterprise": (10000, 50000),
        }
        multipliers = ((1, 2), (3, 5), (8, 14))
        low, high = base_by_size[size_band]
        low_multiplier, high_multiplier = multipliers[plan_index]
        interval_multiplier = {
            "monthly": 1,
            "usage": 1,
            "annual": 10,
            "one_time": 20,
        }[billing_interval]
        minimum = self._round_price(low * low_multiplier * interval_multiplier)
        maximum = self._round_price(
            high * high_multiplier * interval_multiplier, up=True
        )
        return PriceRange(amount_min_usd=minimum, amount_max_usd=maximum)

    def _round_price(self, value: int, up: bool = False) -> int:
        bucket = 50 if value < 1000 else 100
        if up:
            return ((value + bucket - 1) // bucket) * bucket
        return max(bucket, (value // bucket) * bucket)

    def _included_features(self, features: list[str], plan_index: int) -> list[str]:
        if plan_index == 0:
            return features[: min(3, len(features))]
        if plan_index == 1:
            return features[: min(5, len(features))]
        return list(features)

    def _sku(
        self, state: GenerationState, company: Company, slug: str, plan_name: str
    ) -> str:
        sku_base = f"{slug.upper().replace('-', '_')}-{plan_name.upper()}"

        def candidate(attempt: int) -> str:
            return sku_base if attempt == 0 else f"{sku_base}-{attempt + 1}"

        return str(state.registry.unique(f"product-sku:{company.id}", candidate))


class PersonRecordProvider:
    provides = ("person_record",)
    requires = (
        "person",
        "address",
        "company",
        "contact",
        "job",
        "socials",
        "avatar",
        "bio",
        "website",
    )

    def generate(self, state: GenerationState) -> dict[str, object]:
        record = PersonRecord(
            id=state.registry.uuid("person"),
            person=state.facts["person"],
            address=state.facts["address"],
            contact=state.facts["contact"],
            job=state.facts["job"],
            company=state.facts["company"],
            socials=state.facts["socials"],
            avatar=state.facts["avatar"],
            bio=state.facts["bio"],
            website=state.facts["website"],
        )
        return {"person_record": record}


def default_providers() -> tuple[object, ...]:
    return (
        AddressProvider(),
        PersonProvider(),
        IndustryProvider(),
        CompanyProvider(),
        CompanyRecordProvider(),
        JobProvider(),
        ContactProvider(),
        SocialsProvider(),
        WebsiteProvider(),
        AvatarProvider(),
        BioProvider(),
        ProductRecordProvider(),
        PersonRecordProvider(),
    )
