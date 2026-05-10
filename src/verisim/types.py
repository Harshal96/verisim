from __future__ import annotations

from typing import Annotated, Literal

from pydantic import StringConstraints

CountryCode = Annotated[
    str, StringConstraints(pattern=r"^[A-Z]{2}$", min_length=2, max_length=2)
]
LocaleCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}_[A-Z]{2}$")]
PostalCode = Annotated[str, StringConstraints(min_length=3, max_length=12)]
EmailAddress = Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Username = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{1,62}[a-z0-9]$")
]
Url = Annotated[str, StringConstraints(pattern=r"^https?://[^/\s]+.*$")]

SizeBand = Literal["seed", "startup", "SMB", "mid-market", "enterprise"]
FundingStage = Literal[
    "pre-seed",
    "seed",
    "Series A",
    "Series B",
    "Series C+",
    "IPO",
    "bootstrapped",
]
EmailPattern = Literal["first.last", "flast", "first_last", "first"]
LegalEntityType = Literal[
    "LLC",
    "Inc.",
    "Corporation",
    "Ltd",
    "Ltd.",
    "PLC",
    "Pty Ltd",
    "Pvt Ltd",
    "LLP",
    "GmbH",
]

__all__ = [
    "CountryCode",
    "EmailAddress",
    "EmailPattern",
    "FundingStage",
    "LegalEntityType",
    "LocaleCode",
    "PostalCode",
    "SizeBand",
    "Url",
    "Username",
]
