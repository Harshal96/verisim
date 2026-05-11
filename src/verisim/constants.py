from __future__ import annotations

from verisim.types import EmailPattern, FundingStage, LegalEntityType, SizeBand

CANADIAN_NANP_AREA_CODES: frozenset[str] = frozenset(
    {
        "204",
        "236",
        "249",
        "250",
        "289",
        "306",
        "343",
        "365",
        "403",
        "416",
        "418",
        "431",
        "437",
        "438",
        "450",
        "506",
        "514",
        "519",
        "548",
        "579",
        "581",
        "587",
        "604",
        "613",
        "647",
        "705",
        "709",
        "778",
        "780",
        "782",
        "807",
        "819",
        "825",
        "867",
        "902",
        "905",
    }
)

EMAIL_PATTERNS: tuple[EmailPattern, ...] = (
    "first.last",
    "flast",
    "first_last",
    "first",
)
DEFAULT_EMAIL_PATTERN: EmailPattern = "first.last"

SIZE_BAND_EMPLOYEE_RANGES: dict[SizeBand, tuple[int, int]] = {
    "seed": (2, 10),
    "startup": (11, 50),
    "SMB": (51, 250),
    "mid-market": (251, 1000),
    "enterprise": (1001, 10000),
}
SIZE_BAND_AGE_RANGES: dict[SizeBand, tuple[int, int]] = {
    "seed": (0, 2),
    "startup": (1, 6),
    "SMB": (3, 18),
    "mid-market": (7, 35),
    "enterprise": (12, 80),
}
SIZE_BAND_CHOICES_BY_MAX_AGE: tuple[tuple[int, tuple[SizeBand, ...]], ...] = (
    (2, ("seed", "startup")),
    (6, ("startup", "SMB")),
    (12, ("SMB", "mid-market")),
    (25, ("SMB", "mid-market", "enterprise")),
)
SIZE_BAND_CHOICES_FOR_OLDER_COMPANIES: tuple[SizeBand, ...] = (
    "mid-market",
    "enterprise",
)

LEGAL_ENTITY_TYPES_BY_COUNTRY: dict[str, tuple[LegalEntityType, ...]] = {
    "US": ("LLC", "Inc.", "Corporation"),
    "GB": ("Ltd", "PLC"),
    "CA": ("Ltd.", "Inc.", "Corporation"),
    "AU": ("Pty Ltd", "Ltd"),
    "IN": ("Pvt Ltd", "LLP", "Ltd"),
    "DE": ("GmbH",),
    "MX": ("S.A. de C.V.", "S. de R.L."),
    "JP": ("Kabushiki Kaisha", "Godo Kaisha"),
    "FR": ("SARL", "SAS", "SA"),
    "BR": ("Ltda.", "S.A."),
    "CN": ("Ltd.", "Co., Ltd."),
}

DEFAULT_REVENUE_PER_EMPLOYEE = 160_000
MIN_REVENUE = 50_000
REVENUE_ROUNDING_BUCKET = 100_000
REVENUE_PER_EMPLOYEE = {
    "Data Infrastructure": 190_000,
    "Healthcare Technology": 150_000,
    "Financial Services": 230_000,
    "Climate Operations": 130_000,
}
REVENUE_MULTIPLIERS: dict[SizeBand, tuple[float, float]] = {
    "seed": (0.25, 0.85),
    "startup": (0.50, 1.30),
    "SMB": (0.80, 1.80),
    "mid-market": (1.00, 2.20),
    "enterprise": (1.20, 2.60),
}

FUNDING_STAGES_BY_SIZE_BAND: dict[SizeBand, tuple[FundingStage, ...]] = {
    "seed": ("pre-seed", "seed", "bootstrapped"),
    "startup": ("seed", "Series A", "bootstrapped"),
    "SMB": ("Series A", "Series B", "bootstrapped"),
    "mid-market": ("Series B", "Series C+", "bootstrapped"),
    "enterprise": ("Series C+", "IPO", "bootstrapped"),
}

DEPARTMENT_ADDITIONS_BY_SIZE_BAND: dict[SizeBand, tuple[str, ...]] = {
    "seed": ("Founding Team",),
    "startup": ("Engineering", "Product", "Sales", "Operations"),
    "SMB": ("Sales", "Customer Success", "Finance", "People"),
    "mid-market": (
        "Sales",
        "Marketing",
        "Customer Success",
        "Finance",
        "People",
        "Legal",
    ),
    "enterprise": (
        "Sales",
        "Marketing",
        "Customer Success",
        "Finance",
        "People",
        "Legal",
        "Corporate Affairs",
        "Operations",
    ),
}
DEPARTMENT_LIMITS_BY_SIZE_BAND: dict[SizeBand, int] = {
    "seed": 2,
    "startup": 4,
    "SMB": 6,
    "mid-market": 8,
    "enterprise": 10,
}
INDUSTRY_EXECUTIVE_TITLES = {
    "Data Infrastructure": "Chief Data Officer",
    "Healthcare Technology": "Chief Medical Officer",
    "Financial Services": "Chief Risk Officer",
    "Climate Operations": "VP Field Operations",
}

__all__ = [
    "CANADIAN_NANP_AREA_CODES",
    "DEFAULT_EMAIL_PATTERN",
    "DEFAULT_REVENUE_PER_EMPLOYEE",
    "DEPARTMENT_ADDITIONS_BY_SIZE_BAND",
    "DEPARTMENT_LIMITS_BY_SIZE_BAND",
    "EMAIL_PATTERNS",
    "FUNDING_STAGES_BY_SIZE_BAND",
    "INDUSTRY_EXECUTIVE_TITLES",
    "LEGAL_ENTITY_TYPES_BY_COUNTRY",
    "MIN_REVENUE",
    "REVENUE_MULTIPLIERS",
    "REVENUE_PER_EMPLOYEE",
    "REVENUE_ROUNDING_BUCKET",
    "SIZE_BAND_AGE_RANGES",
    "SIZE_BAND_CHOICES_BY_MAX_AGE",
    "SIZE_BAND_CHOICES_FOR_OLDER_COMPANIES",
    "SIZE_BAND_EMPLOYEE_RANGES",
]
