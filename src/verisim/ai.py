from __future__ import annotations

from typing import Protocol

from verisim.models import Company, Job, Person


class ProseAdapter(Protocol):
    def bio(self, person: Person, job: Job, company: Company) -> str: ...


class OfflineProseAdapter:
    """Default no-network prose adapter used by the core package."""

    def bio(self, person: Person, job: Job, company: Company) -> str:
        return (
            f"{person.name} is a {job.title} at {company.name}, "
            f"working in {company.industry}."
        )
