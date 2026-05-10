from __future__ import annotations

from verisim import CompanyRecord, SizeBand, Verisim


def generate_example(seed: int = 123, size_band: SizeBand = "startup") -> CompanyRecord:
    """Generate one coherent synthetic company record."""
    verisim = Verisim(locale="en_US", output_language="en", seed=seed)
    return verisim.generate(CompanyRecord, context={"size_band": size_band})


def main() -> None:
    record = generate_example()
    print(record.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
