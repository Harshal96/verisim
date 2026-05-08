from __future__ import annotations

from collections.abc import Iterable, Mapping
from random import Random
from typing import Literal, TypeVar

from verisim.context import ContextGraph, GenerationState
from verisim.data import LiteDataPack
from verisim.errors import ContextConflictError
from verisim.models import (
    Address,
    Company,
    Contact,
    Dataset,
    DatasetSpec,
    DiagnosticIssue,
    GenerationDiagnostics,
    Job,
    Person,
    PersonRecord,
    Socials,
    Website,
)
from verisim.packs import DataPackManager
from verisim.providers import default_providers
from verisim.registry import UniquenessRegistry

T = TypeVar("T")
ConflictMode = Literal["strict", "repair", "explain"]


class Verisim:
    def __init__(
        self,
        locale: str = "en_US",
        output_language: str = "en",
        script: str = "latin",
        seed: int | None = None,
        data_pack: str | LiteDataPack = "lite",
    ) -> None:
        self.locale = locale
        self.output_language = output_language
        self.script = script
        self.random = Random(seed)
        self.registry = UniquenessRegistry(namespace=f"{locale}:{seed}")
        self.pack_manager = DataPackManager()
        self.data = self.pack_manager.load(data_pack) if isinstance(data_pack, str) else data_pack
        self.graph = ContextGraph(
            providers=default_providers(),
            targets={
                Address: "address",
                Person: "person",
                Company: "company",
                Job: "job",
                Contact: "contact",
                Socials: "socials",
                Website: "website",
                PersonRecord: "person_record",
            },
        )

    def generate(
        self,
        model: type[T],
        context: object | Mapping[str, object] | None = None,
        mode: ConflictMode = "strict",
    ) -> T | GenerationDiagnostics:
        facts = self._facts_from_context(context, target=model)
        diagnostics = self._diagnostics(facts)
        if mode == "explain":
            return diagnostics
        if diagnostics.conflicts:
            if mode == "strict":
                raise ContextConflictError(diagnostics.conflicts)
            if mode == "repair":
                facts = self._repair(facts, diagnostics.conflicts)
            else:
                raise ValueError(f"unknown conflict mode {mode!r}")

        state = GenerationState(
            random=self.random,
            data=self.data,
            registry=self.registry,
            locale=self.locale,
            output_language=self.output_language,
            script=self.script,
            facts=facts,
        )
        return self.graph.generate(model, state)  # type: ignore[return-value]

    def records(self, model: type[T], count: int, context: object | Mapping[str, object] | None = None) -> list[T]:
        return [self.generate(model, context=context) for _ in range(count)]  # type: ignore[list-item]

    def iter_records(
        self,
        model: type[T],
        count: int | None = None,
        context: object | Mapping[str, object] | None = None,
    ) -> Iterable[T]:
        produced = 0
        while count is None or produced < count:
            produced += 1
            yield self.generate(model, context=context)  # type: ignore[misc]

    def dataset(self, spec: DatasetSpec) -> Dataset:
        if spec.people and spec.companies == 0:
            raise ValueError("DatasetSpec.companies must be at least 1 when people are requested")
        companies = [self.generate(Company) for _ in range(spec.companies)]
        people: list[PersonRecord] = []
        for index in range(spec.people):
            company = companies[index % len(companies)]
            people.append(self.generate(PersonRecord, context={"company": company}, mode="repair"))  # type: ignore[arg-type]
        return Dataset(people=people, companies=companies)

    def _facts_from_context(self, context: object | Mapping[str, object] | None, target: type) -> dict[str, object]:
        if context is None:
            return {}
        if isinstance(context, Mapping):
            return self._facts_from_mapping(context)
        facts: dict[str, object] = {}
        self._add_fact(facts, context, target)
        return facts

    def _facts_from_mapping(self, mapping: Mapping[str, object]) -> dict[str, object]:
        facts: dict[str, object] = {}
        for key, value in mapping.items():
            if key in {
                "address",
                "person",
                "company",
                "job",
                "contact",
                "socials",
                "website",
                "avatar",
                "bio",
                "person_record",
                "industry_data",
            }:
                facts[key] = value
            else:
                self._add_fact(facts, value, target=object)
        return facts

    def _add_fact(self, facts: dict[str, object], value: object, target: type) -> None:
        if isinstance(value, PersonRecord):
            if target is PersonRecord:
                facts["person_record"] = value
                return
            facts.update(
                {
                    "person": value.person,
                    "address": value.address,
                    "contact": value.contact,
                    "job": value.job,
                    "company": value.company,
                    "avatar": value.avatar,
                    "bio": value.bio,
                    "website": value.website,
                }
            )
            if target is not Socials:
                facts["socials"] = value.socials
            return
        fact_by_type = {
            Address: "address",
            Person: "person",
            Company: "company",
            Job: "job",
            Contact: "contact",
            Socials: "socials",
            Website: "website",
        }
        for model_type, fact in fact_by_type.items():
            if isinstance(value, model_type):
                facts[fact] = value
                if isinstance(value, Company):
                    facts["industry"] = value.industry
                return

    def _diagnostics(self, facts: Mapping[str, object]) -> GenerationDiagnostics:
        conflicts: list[DiagnosticIssue] = []
        address = facts.get("address")
        contact = facts.get("contact")
        job = facts.get("job")
        company = facts.get("company")

        if isinstance(address, Address):
            postal_codes = self.data.postal_codes_for_city(address.country_code, address.region_code, address.city)
            if not postal_codes or address.postal_code not in postal_codes:
                conflicts.append(
                    DiagnosticIssue(
                        code="address.postal_code",
                        message=(
                            f"postal code {address.postal_code} does not belong to "
                            f"{address.city}, {address.region_code}, {address.country_code}"
                        ),
                        path="address.postal_code",
                    )
                )
        if isinstance(address, Address) and isinstance(contact, Contact):
            if contact.phone.country_code != address.country_code:
                conflicts.append(
                    DiagnosticIssue(
                        code="contact.phone.country",
                        message=(
                            f"phone country {contact.phone.country_code} does not match "
                            f"address country {address.country_code}"
                        ),
                        path="contact.phone",
                    )
                )
        if isinstance(job, Job) and isinstance(company, Company) and job.industry != company.industry:
            conflicts.append(
                DiagnosticIssue(
                    code="job.company.industry",
                    message=f"job industry {job.industry} does not match company industry {company.industry}",
                    path="job.industry",
                )
            )
        return GenerationDiagnostics(ok=not conflicts, conflicts=conflicts)

    def _repair(self, facts: dict[str, object], conflicts: list[DiagnosticIssue]) -> dict[str, object]:
        repaired = dict(facts)
        for conflict in conflicts:
            if conflict.code == "contact.phone.country":
                repaired.pop("contact", None)
            elif conflict.code == "address.postal_code":
                repaired.pop("address", None)
            elif conflict.code == "job.company.industry":
                repaired.pop("job", None)
        repaired.pop("person_record", None)
        return repaired
