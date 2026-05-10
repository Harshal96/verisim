from __future__ import annotations

from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from verisim.constants import CANADIAN_NANP_AREA_CODES
from verisim.types import (
    CountryCode,
    EmailAddress,
    EmailPattern,
    FundingStage,
    LegalEntityType,
    LocaleCode,
    PostalCode,
    SizeBand,
    Url,
    Username,
)


class VerisimModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class GeoPoint(VerisimModel):
    latitude: float
    longitude: float


class PhoneNumber(VerisimModel):
    e164: str
    national: str
    country_code: CountryCode
    country_calling_code: str

    @classmethod
    def from_string(cls, value: str) -> "PhoneNumber":
        raw = value.strip()
        digits = "".join(character for character in raw if character.isdigit())
        if raw.startswith("+1") or (len(digits) == 11 and digits.startswith("1")):
            core = digits[1:] if digits.startswith("1") else digits
            area, exchange, line = core[:3], core[3:6], core[6:10]
            country_code = "CA" if area in CANADIAN_NANP_AREA_CODES else "US"
            return cls(
                e164=f"+1{area}{exchange}{line}",
                national=f"({area}) {exchange}-{line}",
                country_code=country_code,
                country_calling_code="+1",
            )
        if raw.startswith("+91") or (len(digits) == 12 and digits.startswith("91")):
            core = digits[2:] if digits.startswith("91") else digits
            return cls(
                e164=f"+91{core[:10]}",
                national=f"{core[:5]} {core[5:10]}",
                country_code="IN",
                country_calling_code="+91",
            )
        if raw.startswith("+44") or digits.startswith("44"):
            core = digits[2:] if digits.startswith("44") else digits
            return cls(
                e164=f"+44{core}",
                national=f"0{core[:2]} {core[2:6]} {core[6:]}".strip(),
                country_code="GB",
                country_calling_code="+44",
            )
        if raw.startswith("+61") or digits.startswith("61"):
            core = digits[2:] if digits.startswith("61") else digits
            return cls(
                e164=f"+61{core}",
                national=f"0{core[:1]} {core[1:5]} {core[5:]}".strip(),
                country_code="AU",
                country_calling_code="+61",
            )
        if raw.startswith("+49") or digits.startswith("49"):
            core = digits[2:] if digits.startswith("49") else digits
            return cls(
                e164=f"+49{core}",
                national=f"0{core}",
                country_code="DE",
                country_calling_code="+49",
            )
        return cls(
            e164=f"+{digits}",
            national=raw,
            country_code="US",
            country_calling_code="+1",
        )


class Website(VerisimModel):
    url: Url
    host: str

    @classmethod
    def from_host(cls, host: str, path: str = "") -> "Website":
        normalized_path = path if not path or path.startswith("/") else f"/{path}"
        return cls(url=f"https://{host}{normalized_path}", host=host)

    def __str__(self) -> str:
        return self.url


class Address(VerisimModel):
    line1: str
    city: str
    region: str
    region_code: str
    postal_code: PostalCode
    country: str
    country_code: CountryCode
    line2: str | None = None
    geo: GeoPoint | None = None

    @field_validator("country_code", "region_code")
    @classmethod
    def uppercase_code(cls, value: str) -> str:
        return value.upper()


class Person(VerisimModel):
    given_name: str
    family_name: str
    name: str
    username: Username
    birthdate: str
    locale: LocaleCode


class Company(VerisimModel):
    id: UUID
    name: str
    industry: str
    domain: str
    website: Website
    address: Address | None = None


class IncorporationJurisdiction(VerisimModel):
    country: str
    country_code: CountryCode
    region: str
    region_code: str

    @field_validator("country_code", "region_code")
    @classmethod
    def uppercase_code(cls, value: str) -> str:
        return value.upper()


class RevenueRange(VerisimModel):
    annual_min_usd: int = Field(ge=0)
    annual_max_usd: int = Field(ge=0)
    currency: Literal["USD"] = "USD"


class Job(VerisimModel):
    title: str
    industry: str
    department: str
    level: str
    company_id: UUID | None = None


class Contact(VerisimModel):
    email: EmailAddress
    phone: PhoneNumber

    @field_validator("phone", mode="before")
    @classmethod
    def parse_phone(cls, value: PhoneNumber | str) -> PhoneNumber:
        if isinstance(value, PhoneNumber):
            return value
        return PhoneNumber.from_string(str(value))

    @classmethod
    def synthetic(cls, email: str, phone: PhoneNumber | str) -> "Contact":
        return cls(email=email, phone=phone)


class SocialAccount(VerisimModel):
    platform: Literal["x", "instagram", "linkedin", "github"]
    handle: Username
    url: Url


class Socials(VerisimModel):
    x: SocialAccount
    instagram: SocialAccount
    linkedin: SocialAccount
    github: SocialAccount

    def handles(self) -> list[str]:
        return [
            self.x.handle,
            self.instagram.handle,
            self.linkedin.handle,
            self.github.handle,
        ]


class LeadershipMember(VerisimModel):
    person: Person
    title: str
    department: str | None = None


class CompanyRecord(VerisimModel):
    id: UUID
    name: str
    legal_entity_type: LegalEntityType
    founded_year: int = Field(ge=1800)
    industry: str
    size_band: SizeBand
    employee_count: int = Field(ge=1)
    revenue_range: RevenueRange
    funding_stage: FundingStage
    headquarters: Address
    incorporated_in: IncorporationJurisdiction
    domain: str
    website: Website
    email_pattern: EmailPattern
    linkedin_slug: Username
    departments: list[str] = Field(min_length=1)
    leadership: list[LeadershipMember] = Field(min_length=1)

    def as_company(self) -> Company:
        return Company(
            id=self.id,
            name=self.name,
            industry=self.industry,
            domain=self.domain,
            website=self.website,
            address=self.headquarters,
        )


class PersonRecord(VerisimModel):
    id: UUID
    person: Person
    address: Address
    contact: Contact
    job: Job
    company: Company
    socials: Socials
    avatar: Url
    bio: str
    website: Website


class DatasetSpec(VerisimModel):
    people: int = Field(default=10, ge=0)
    companies: int = Field(default=3, ge=0)
    people_per_company: dict[SizeBand, int] | None = None


class Dataset(VerisimModel):
    people: list[PersonRecord]
    companies: list[CompanyRecord]


class DiagnosticIssue(VerisimModel):
    code: str
    message: str
    path: str


class GenerationDiagnostics(VerisimModel):
    ok: bool
    conflicts: list[DiagnosticIssue] = Field(default_factory=list)


class PackMetadata(VerisimModel):
    name: str
    version: str
    scope: str
    provenance: Sequence[str]
    signed: bool
