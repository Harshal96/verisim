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
    "S.A. de C.V.",
    "S. de R.L.",
    "Kabushiki Kaisha",
    "Godo Kaisha",
    "SARL",
    "SAS",
    "SA",
    "Ltda.",
    "S.A.",
    "Co., Ltd.",
]
ProductType = Literal[
    "software",
    "platform",
    "data_product",
    "managed_service",
    "program",
    "financial_product",
]
ProductLifecycleStage = Literal["beta", "launched", "growth", "mature"]
PricingModel = Literal[
    "subscription", "usage_based", "contract", "transaction", "project"
]
BillingInterval = Literal["monthly", "annual", "usage", "one_time"]

__all__ = [
    "BillingInterval",
    "CountryCode",
    "EmailAddress",
    "EmailPattern",
    "FundingStage",
    "LegalEntityType",
    "LocaleCode",
    "PostalCode",
    "PricingModel",
    "ProductLifecycleStage",
    "ProductType",
    "SizeBand",
    "Url",
    "Username",
]
