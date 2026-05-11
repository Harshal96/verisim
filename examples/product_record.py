from __future__ import annotations

from verisim import CompanyRecord, ProductRecord, SizeBand, Verisim


def generate_example(seed: int = 123, size_band: SizeBand = "startup") -> ProductRecord:
    """Generate one coherent synthetic product record for a company."""
    verisim = Verisim(locale="en_US", output_language="en", seed=seed)
    company = verisim.generate(CompanyRecord, context={"size_band": size_band})
    return verisim.generate(ProductRecord, context={"company": company})


def main() -> None:
    record = generate_example()
    print(record.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
