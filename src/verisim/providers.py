from __future__ import annotations

from datetime import date
from random import Random

from verisim.context import GenerationState
from verisim.data import IndustryData, NameData
from verisim.models import (
    Company,
    Contact,
    Job,
    Person,
    PersonRecord,
    PhoneNumber,
    SocialAccount,
    Socials,
    Website,
)
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


class JobProvider:
    provides = ("job",)
    requires = ("company",)

    def generate(self, state: GenerationState) -> dict[str, object]:
        company = state.facts["company"]
        assert isinstance(company, Company)
        industry = _industry_by_name(state, company.industry)
        return {
            "job": Job(
                title=state.random.choice(industry.titles),
                industry=company.industry,
                department=state.random.choice(industry.departments),
                level=state.random.choice(industry.levels),
                company_id=company.id,
            )
        }


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
        city_part = "mail"
        address = state.facts.get("address")
        if address is not None:
            city_part = ascii_slug(getattr(address, "city", "mail"))
        base = username_slug(person.username, separator=".")

        def candidate(attempt: int) -> str:
            local = base if attempt == 0 else f"{base}.{attempt + 1}"
            return f"{local}@{city_part}.example.invalid"

        return str(state.registry.unique("email", candidate))

    def _phone(
        self, state: GenerationState, country_code: str, address: object
    ) -> PhoneNumber:
        base = state.registry.next_index(f"phone-sequence:{country_code}")

        def candidate(attempt: int) -> str:
            sequence = base + attempt
            if country_code == "IN":
                subscriber = f"{9000000000 + (sequence % 999999):010d}"
                return PhoneNumber(
                    e164=f"+91{subscriber}",
                    national=f"{subscriber[:5]} {subscriber[5:]}",
                    country_code="IN",
                    country_calling_code="+91",
                ).e164

            city = (
                state.data.city_for_address(address)
                if hasattr(address, "postal_code")
                else None
            )
            area = state.random.choice(city.area_codes) if city is not None else "555"
            line = sequence % 10_000
            return PhoneNumber(
                e164=f"+1{area}555{line:04d}",
                national=f"({area}) 555-{line:04d}",
                country_code="US",
                country_calling_code="+1",
            ).e164

        e164 = str(state.registry.unique("phone", candidate))
        return PhoneNumber.from_string(e164)


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


class PersonRecordProvider:
    provides = ("person_record",)
    requires = (
        "person",
        "address",
        "contact",
        "job",
        "company",
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
        JobProvider(),
        ContactProvider(),
        SocialsProvider(),
        WebsiteProvider(),
        AvatarProvider(),
        BioProvider(),
        PersonRecordProvider(),
    )
